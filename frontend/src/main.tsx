import React from 'react';
import ReactDOM from 'react-dom/client';
import { GoogleOAuthProvider } from '@react-oauth/google';
import { App } from './App';
import './index.css';

// Get Google Client ID from environment or use placeholder
const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || '1234567890-abc123.apps.googleusercontent.com';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <GoogleOAuthProvider clientId={googleClientId}>
      <App />
    </GoogleOAuthProvider>
  </React.StrictMode>
);

