# Security Analysis Report

**Date:** 2026-02-21
**Scope:** Full codebase — `lagasafn/`, `codex-api/`, `deployment/`, scripts

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | 1     |
| High     | 2     |
| Medium   | 5     |
| Low      | 3     |

---

## CRITICAL

### SEC-001 — Hardcoded Placeholder Secrets in Kubernetes Deployment

**File:** `deployment/secret.yaml:8-9`
**Impact:** Full application compromise if deployed as-is.

The Kubernetes `Secret` manifest ships with placeholder values that base64-decode to the literal string `"secret-string"`:

```yaml
data:
  SECRET_KEY: c2VjcmV0LXN0cmluZwo=     # decodes to: secret-string
  API_ACCESS_TOKEN: c2VjcmV0LXN0cmluZwo= # decodes to: secret-string
```

Django's `SECRET_KEY` is used to sign sessions, CSRF tokens, and password-reset links. An attacker who knows this value can forge any of these. The `API_ACCESS_TOKEN` controls all authenticated POST/PUT endpoints (`bill_meta`, `bill_validate`, `bill_publish`).

**Recommendation:**
- Remove `secret.yaml` from version control entirely, or replace its contents with proper secret references (e.g., sealed-secrets, Vault, or environment-specific CI injection).
- Rotate any instance of these secrets immediately if the file was ever applied to a real cluster.
- Add `deployment/secret.yaml` to `.gitignore` (or use a `.yaml.example` pattern).

---

## HIGH

### SEC-002 — XPath Injection via Unauthenticated API Endpoint

**File:** `lagasafn/pathing.py:640` (called from `codex-api/law/api.py:85-96`)
**Impact:** Arbitrary XPath execution against XML data files; potential DoS via crafted queries.

The `/api/law/get-segment/` endpoint accepts a raw `xpath` query parameter and passes it directly to `lxml`'s `xml.xpath()` with no sanitization:

```python
# codex-api/law/api.py
def api_get_segment(request, law_nr: str, law_year: int, xpath: str):
    return get_segment(law_nr, law_year, xpath)

# lagasafn/pathing.py
def get_segment(law_nr, law_year, xpath):
    xml = etree.parse(XML_FILENAME % ...).getroot()
    elements = xml.xpath(xpath)   # ← user input executed here
```

An attacker can:
- Extract data outside the intended scope (e.g., `xpath=//sen` to dump all sentences from a law)
- Cause a DoS through computationally expensive expressions (e.g., `//node()[count(ancestor::*)>100]`)
- Potentially trigger `lxml` extension functions depending on build flags

**Recommendation:**
- Validate that the `xpath` parameter matches a strict allowlist pattern before evaluation (e.g., only allow XPath expressions that start from known safe anchors).
- Alternatively, accept structured parameters (element type, nr-attribute values) instead of raw XPath, and build the expression server-side.

---

### SEC-003 — Pickle Deserialization of Search Index

**File:** `lagasafn/search.py:107`
**Impact:** Remote code execution if the index file is replaced by an attacker.

The search engine loads its index using Python's `pickle` module:

```python
fh = open(self._index_file, "rb")
self._index = pickle.load(fh)   # ← arbitrary code execution if file is malicious
```

The index path is `data/search_index.pkl`. If an attacker gains write access to this file (e.g., through a compromised deployment pipeline, a writable data volume, or another write vulnerability), they can execute arbitrary Python code on the server at startup or on next search-engine reload.

**Recommendation:**
- Replace `pickle` with a safe serialisation format such as `json`, `msgpack`, or `shelve` with integrity checks.
- If `pickle` must be kept, cryptographically sign the file at build time and verify the signature before loading.
- Ensure the file is not writable by the web-server process.

---

## MEDIUM

### SEC-004 — Unauthenticated XML Upload with No Size Limit (DoS / XML Bomb)

**File:** `codex-api/law/api.py:99-133`
**Impact:** Denial-of-service via Billion Laughs or large file upload.

The `/api/law/normalize/` endpoint accepts arbitrary XML uploads without authentication and without a payload-size limit:

```python
@router.post("normalize/")          # ← no auth= argument
def api_normalize(request, input_file: UploadedFile = File(...)):
    input_data = input_file.read()
    xml_doc = etree.fromstring(input_data)   # ← no defusedxml, no size check
```

`lxml.etree.fromstring` is vulnerable to XML entity expansion attacks (Billion Laughs / quadratic blowup) unless entity expansion is explicitly disabled.

**Recommendation:**
- Protect the endpoint with `auth=APIAuthentication()` or add a separate rate-limiting middleware.
- Add a maximum upload size check before parsing.
- Use `defusedxml` or disable entity resolution: `parser = etree.XMLParser(resolve_entities=False, no_network=True)`.

---

### SEC-005 — Unvalidated File Path in `law_show_patched`

**File:** `codex-api/law/views.py:100-131`
**Impact:** Information disclosure; unhandled exception on missing files.

The `law_show_patched` view constructs a file path from the user-provided URL segment `identifier` without validating that `law_nr` and `law_year` contain only digits:

```python
law_nr, law_year = identifier.split("/")

# No digit check on law_nr or law_year
filename = "%s-%s.html" % (law_year, law_nr)

fullpath = join(settings.DATA_DIR, "..", "patched", filename)
if not isfile(fullpath):
    fullpath = join(settings.DATA_DIR, "..", "cleaned", filename)

with open(fullpath, "r") as f:    # FileNotFoundError → 500 if neither path exists
    content = f.read()

return HttpResponse(content, content_type="text/html")  # raw HTML, no sanitisation
```

While direct path traversal is blocked by the filename format (the `/` separator is consumed by `split`), sending a non-existent identifier causes an uncaught `FileNotFoundError` (HTTP 500), which may leak stack traces if `DEBUG` is enabled. Additionally, the file content is returned as-is with `content_type="text/html"` without sanitisation — if the file contained attacker-controlled content, that content would be rendered in the browser.

**Recommendation:**
- Validate that `law_nr` and `law_year` match expected formats (digits or the `m\d+d\d+` pre-1885 pattern) before building the path.
- Wrap `open()` in a try/except and return `Http404` on `FileNotFoundError`.

---

### SEC-006 — URL Injection in External API Call

**File:** `lagasafn/chaostemple/service.py:24-26`
**Impact:** Server-side request forgery (SSRF) or parameter injection.

The `law_identifier` argument is interpolated directly into a URL query string without URL encoding:

```python
def law_document(law_identifier: str) -> dict:
    url = "%s/law_document?law_identifier=%s" % (CHAOSTEMPLE_API_URL, law_identifier)
    return _get(url)
```

If `law_identifier` contains `&`, `#`, or other URL metacharacters (e.g., `5/1995&admin=true`), additional query parameters can be injected into the request sent to the Chaostemple API.

**Recommendation:**
- Use `urllib.parse.urlencode` or `requests`'s `params=` argument:
  ```python
  response = requests.get(url, params={"law_identifier": law_identifier})
  ```

---

### SEC-007 — No Rate Limiting on Any API Endpoint

**File:** `codex-api/law/api.py`, `codex-api/advert/api.py`, `codex-api/bill/api.py`
**Impact:** Denial-of-service through resource exhaustion; credential brute-force.

None of the Django Ninja API endpoints configure any rate limiting. The search endpoint (`/api/law/search/`) is particularly expensive (full-text search with TF-IDF scoring) and can be abused freely. The authenticated bill endpoints could have their token brute-forced without any lockout.

**Recommendation:**
- Add a Django rate-limiting middleware (e.g., `django-ratelimit`) or use an upstream reverse proxy (nginx/Traefik) to throttle requests.

---

### SEC-008 — Git Commit Triggered via HTTP Endpoint

**File:** `codex-api/bill/api.py:76-145`
**Impact:** Uncontrolled git repository growth; side-channel for file-write via an authenticated token.

The `bill_publish` endpoint writes user-supplied XML to disk and then commits it to the repository:

```python
repo = Repo.init(BASE_DIR)
repo.index.add(existing_filename)
repo.index.commit("Publish bill nr. " + str(bill_nr) + "/" + CURRENT_PARLIAMENT_VERSION + ...)
```

An attacker who obtains (or guesses) the `API_ACCESS_TOKEN` can:
1. Write arbitrary XML content to `data/bills/` paths under attacker-chosen filenames.
2. Permanently embed that content in git history.
3. Exhaust disk space through repeated calls.

The retry loop on git lock also introduces a predictable sleep-based timing vector.

**Recommendation:**
- Re-evaluate whether auto-committing via HTTP is necessary; prefer out-of-band CI/CD for persistence.
- If the commit behaviour must be kept, ensure the `bill_nr` and law attributes are strictly validated as integers before use.
- Add a per-IP or per-token rate limit on this endpoint.

---

## LOW

### SEC-009 — `DEBUG = True` Hardcoded in Library Settings

**File:** `lagasafn/settings.py:12`
**Impact:** Verbose error output; potential information disclosure in misconfigured environments.

```python
DEBUG = True
```

The `lagasafn` library's own settings module has `DEBUG` hardcoded to `True`. Although the Django application correctly reads this from environment variables (`local_settings.py`), any tooling or script that imports `lagasafn.settings` directly will operate in debug mode, which may expose stack traces or other diagnostic information.

**Recommendation:**
- Default to `DEBUG = False` and allow it to be overridden via an environment variable.

---

### SEC-010 — CORS Only Allows HTTP Localhost

**File:** `codex-api/mechlaw/settings.py:133-135`
**Impact:** Development-only origin permanently configured; no HTTPS equivalent.

```python
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
]
```

This configuration has no production counterpart in the committed code. The production front-end origin is never added. If `CORS_ALLOWED_ORIGINS` is not overridden at deploy time, the API will reject legitimate cross-origin requests from the production UI.

**Recommendation:**
- Add the production UI origin (with HTTPS) to `deployment/configmap.yaml` and consume it in `local_settings.py`.

---

### SEC-011 — Broad Exception Suppression Hides Security-Relevant Errors

**Files:** `codex-api/bill/api.py:135`, `lagasafn/pathing.py:637`
**Impact:** Silent failure may mask exploitation attempts.

Multiple `except Exception` clauses silently swallow errors:

```python
# bill/api.py — git commit loop
except Exception:
    failureCnt += 1
    sleep(failureCnt * 1)

# pathing.py — XML parse failure
except:
    raise NoSuchLawException()
```

A bare `except:` catches even `SystemExit` and `KeyboardInterrupt`. Silent swallowing of git exceptions means repeated failures go unlogged.

**Recommendation:**
- Replace bare `except:` with `except (etree.XMLSyntaxError, OSError):` (or similar specific types).
- Add logging for unexpected exceptions at minimum `WARNING` level.

---

## Appendix — Informational Notes

- **`lagasafn/utils.py:340`**: `subprocess.check_output(["stty", "size"])` is used only in the interactive CLI tool (`ask_user_about_location`) and is not reachable via HTTP. No injection risk identified.
- **`lagasafn/advert/remote.py`**: Fetches HTML from `www.stjornartidindi.is` and parses it with `BeautifulSoup`/`lxml`. Remote content is treated as data (not executed), but if the upstream site were compromised, malformed XML/HTML could potentially trigger `lxml` parser bugs.
- **Django Admin (`/admin/`)**: Exposed at the default path without additional IP restriction. Consider restricting access via middleware or reverse-proxy ACL in production.
