# Checks if the outcome on our web is identical to the source data.
[group('codex-api')]
web:
    #!/usr/bin/env bash
    set -e
    cd ../codex-api
    python3 manage.py test tests.WebTests

# Tests if applying adverts works.
[group('codex-api')]
advert-applying:
    #!/usr/bin/env bash
    set -e
    cd ../codex-api
    python3 manage.py test tests.AdvertApplyingTests
