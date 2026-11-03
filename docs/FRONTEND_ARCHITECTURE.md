# Frontend architecture

`src/main.jsx` composes the HashRouter shell, shared navigation/footer, route-level page components and demo dialogs. Reusable `Title` and `EventCard` components share the visual language. `src/style.css` owns all visual styling, responsive rules, focus treatment and reduced-motion preferences.

`src/config/convention.config.js` stores edition-wide data. `src/data/events.js` and `navigation.js` are local datasets. `src/utils/` contains pricing and eligibility logic without UI dependencies. `src/services/mockServices.js` defines the future replacement boundary. Components currently use the shared mock event dataset directly in a small prototype; moving reads fully behind service hooks is an appropriate next frontend refactor before API integration.

HashRouter emits `/#/route` URLs for GitHub Pages. Vite base path comes from `VITE_BASE_PATH`; public supplied image URLs use `import.meta.env.BASE_URL` with URL-encoded relative paths. The API migration should preserve page-level components and replace mock service implementations, then add loading/error states as real requests are introduced.
