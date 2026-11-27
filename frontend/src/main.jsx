import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.jsx';
import { AuthProvider } from './lib/auth.jsx';
import { SiteProvider } from './lib/site.jsx';
import { ThemeProvider } from './lib/theme.jsx';
import { ThemeProvider as MuiThemeProvider } from '@mui/material/styles';
import { muiTheme } from './lib/muiTheme.js';
import './style.css';
import './theme.css';
import './styles/poi.css';
import './styles/nav.css';
import './styles/inner-pages.css';
import './styles/android.css';

// Automatically migrate legacy hash URLs (e.g. /#/manage/policy -> /manage/policy)
if (
  typeof window !== 'undefined' &&
  window.location.hash &&
  window.location.hash.startsWith('#/')
) {
  const cleanPath = window.location.hash.slice(1);
  window.history.replaceState(null, '', cleanPath);
}

// Developer badge Easter egg (Favicon & Portfolio HUD)
if (typeof window !== 'undefined') {
  console.log(
    '%c             .         :         .\n' +
      '        -----+---------+---------+-----\n' +
      '             |   %c\\===========/%c   |\n' +
      '             |    %c\\         /%c    |\n' +
      '        %c=====[  M I D H U N   K   M  ]=====%c\n' +
      '             |      %c\\     /%c      |\n' +
      '             |       %c\\   /%c       |\n' +
      '             |        %c\\ /%c        |\n' +
      '             |         %cV%c         |\n' +
      '        -----+---------+---------+-----\n' +
      "             '         :         '",
    'color:#64748b;font-family:monospace;font-size:11px;line-height:1.25;',
    'color:#ef4444;font-weight:900;font-family:monospace;font-size:11px;line-height:1.25;',
    'color:#64748b;font-family:monospace;font-size:11px;line-height:1.25;',
    'color:#ef4444;font-weight:900;font-family:monospace;font-size:11px;line-height:1.25;',
    'color:#64748b;font-family:monospace;font-size:11px;line-height:1.25;',
    'color:#ffffff;background:#090d16;font-weight:800;letter-spacing:1px;font-family:monospace;font-size:11px;line-height:1.25;padding:1px 4px;',
    'color:#64748b;font-family:monospace;font-size:11px;line-height:1.25;',
    'color:#ef4444;font-weight:900;font-family:monospace;font-size:11px;line-height:1.25;',
    'color:#64748b;font-family:monospace;font-size:11px;line-height:1.25;',
    'color:#ef4444;font-weight:900;font-family:monospace;font-size:11px;line-height:1.25;',
    'color:#64748b;font-family:monospace;font-size:11px;line-height:1.25;',
    'color:#ef4444;font-weight:900;font-family:monospace;font-size:11px;line-height:1.25;',
    'color:#64748b;font-family:monospace;font-size:11px;line-height:1.25;',
    'color:#ef4444;font-weight:900;font-family:monospace;font-size:11px;line-height:1.25;',
    'color:#64748b;font-family:monospace;font-size:11px;line-height:1.25;',
  );

  console.log(
    '%c PARALLAX 2027 %c Engineered by Midhun K M ',
    'background:#0a3d42;color:#b8f23d;font-weight:700;padding:4px 8px;border-radius:3px 0 0 3px;font-family:monospace;font-size:11px;',
    'background:#1e293b;color:#f8fafc;padding:4px 8px;border-radius:0 3px 3px 0;font-family:monospace;font-size:11px;',
  );

  console.log(
    '%c⚡ Portfolio : %chttps://midhunkm.pages.dev/',
    'color:#94a3b8;font-weight:bold;font-family:monospace;font-size:11px;',
    'color:#38bdf8;font-weight:bold;font-family:monospace;font-size:11px;text-decoration:underline;',
  );
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <MuiThemeProvider theme={muiTheme}>
          <SiteProvider>
            <AuthProvider>
              <App />
            </AuthProvider>
          </SiteProvider>
        </MuiThemeProvider>
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
);

// Register the service worker for app-like, offline-capable repeat visits
// (production only, so dev HMR is never intercepted).
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      /* registration is a progressive enhancement; ignore failures */
    });
  });
}
