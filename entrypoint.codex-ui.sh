#!/bin/sh
# Runs before nginx starts (via /docker-entrypoint.d/).
# 1. Replaces the build-time base path placeholder with the runtime BASE_PATH in all
#    static files (index.html, JS chunks, CSS). The JS chunks need this because Vite
#    embeds the base path as a string literal for code-split dynamic imports.
# 2. Injects runtime environment variables as an inline script into index.html so
#    they are available as window._env_ before the SPA initializes.

# Strip trailing slash so "/" becomes "" and "/new/" becomes "/new".
BASE_PATH_CLEAN="${BASE_PATH%/}"

find /usr/share/nginx/html -type f \( -name "*.html" -o -name "*.js" -o -name "*.css" \) \
    -exec sed -i "s|/__CODEX_UI_BASE_PATH__|${BASE_PATH_CLEAN}|g" {} \;

sed -i "s|</head>|<script>window._env_={VITE_SERVER_BASE_URL:'${VITE_SERVER_BASE_URL:-http://localhost:8000}',BASE_PATH:'${BASE_PATH:-/}'};</script></head>|" \
    /usr/share/nginx/html/index.html
