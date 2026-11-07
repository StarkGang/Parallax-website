import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.jsx';
import { AuthProvider } from './lib/auth.jsx';
import { SiteProvider } from './lib/site.jsx';
import { ThemeProvider } from './lib/theme.jsx';
import './style.css';
import './theme.css';
import './styles/poi.css';
import './styles/nav.css';

// Automatically migrate legacy hash URLs (e.g. /#/manage/policy -> /manage/policy)
if (typeof window !== 'undefined' && window.location.hash && window.location.hash.startsWith('#/')) {
  const cleanPath = window.location.hash.slice(1);
  window.history.replaceState(null, '', cleanPath);
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <SiteProvider>
          <AuthProvider>
            <App />
          </AuthProvider>
        </SiteProvider>
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
);
