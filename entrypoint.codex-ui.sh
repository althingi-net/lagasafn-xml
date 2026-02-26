#!/bin/sh
# Runs before nginx starts (via /docker-entrypoint.d/).
# Injects runtime environment variables as an inline script into index.html so
# they are available as window._env_ before the SPA initializes. This approach
# is used instead of a separate config.js file to avoid any dependency on the
# framework including a script reference in the generated HTML.
sed -i "s|</head>|<script>window._env_={VITE_SERVER_BASE_URL:'${VITE_SERVER_BASE_URL:-http://localhost:8000}'};</script></head>|" \
    /usr/share/nginx/html/index.html
