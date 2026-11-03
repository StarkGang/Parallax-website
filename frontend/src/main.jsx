import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.jsx';
import { AuthProvider } from './lib/auth.jsx';
import { SiteProvider } from './lib/site.jsx';
import './style.css';
import './theme.css';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <SiteProvider>
        <AuthProvider>
          <App />
        </AuthProvider>
      </SiteProvider>
    </BrowserRouter>
  </StrictMode>,
);
