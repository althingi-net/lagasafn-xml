import { Router } from '@solidjs/router';
import { FileRoutes } from '@solidjs/start/router';
import { ErrorBoundary, Suspense } from 'solid-js';
import './app.css';
import './law.css';
import { OpenAPI } from './api';

// Configure the API base URL from runtime config (window._env_) with fallback
// to the build-time env var for local development without a config.js.
OpenAPI.BASE = (window as any)._env_?.VITE_SERVER_BASE_URL
    ?? import.meta.env.VITE_SERVER_BASE_URL
    ?? 'http://localhost:8000';

export default function App() {
    return (
        <Router
            base="/new"
            root={props => (
                <ErrorBoundary fallback={(err) => (
                    <div class="p-8 text-white">
                        <p class="text-lg font-semibold mb-2">Something went wrong</p>
                        <p class="text-white/70">
                            {err instanceof TypeError
                                ? `Could not connect to the server at ${OpenAPI.BASE}. Is it running?`
                                : err.message}
                        </p>
                    </div>
                )}>
                    <Suspense>{props.children}</Suspense>
                </ErrorBoundary>
            )}
        >
            <FileRoutes />
        </Router>
    );
}
