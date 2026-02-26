// Runtime configuration. In production this file is overwritten at container
// startup by the nginx entrypoint script using the pod's environment variables.
window._env_ = {
    VITE_SERVER_BASE_URL: 'http://localhost:8000',
};
