import { Router } from '@solidjs/router';
import { FileRoutes } from '@solidjs/start/router';
import { Suspense } from 'solid-js';
import './app.css';
import './law.css';
import { OpenAPI } from './api';

// Configure the API base URL
OpenAPI.BASE = process.env.VITE_SERVER_BASE_URL ?? 'http://localhost:8000';

export default function App() {
    return (
        <Router
            root={props => (
                <>
                    <Suspense>{props.children}</Suspense>
                </>
            )}
        >
            <FileRoutes />
        </Router>
    );
}
