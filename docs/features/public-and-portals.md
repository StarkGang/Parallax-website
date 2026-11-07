# Public Site and Portals

This document summarizes the user-facing surfaces implemented by the React SPA and backed by `/api/v1`.

## SPA routing

- Router: `react-router-dom` `BrowserRouter` (`frontend/src/main.jsx`).
- Route composition: `frontend/src/App.jsx`.
- Hosting implication: path-based routes require rewrite/fallback to `index.html` (see `vercel.json`, Render/static hosting guidance).

## Public pages

Public routes/pages present information and content for the event (landing/home, event details/sections, and related public views). Exact route paths/components should be confirmed in `frontend/src/App.jsx` and `frontend/src/pages/*`.

## Participant flows

Participant-facing surfaces typically involve authenticated context and server-managed state (registration/participation, team-related actions, verification, and payment-related steps where applicable). Behavior depends on backend rules, feature flags/config, and current edition data.

## Admin flows

Admin surfaces are intended for authorized management operations exposed by admin API routes. Access control is enforced by backend authorization; UI visibility alone is not sufficient.

## Integration-sensitive features

- **Google OAuth:** available only when configured/enabled.
- **Payments (Razorpay/mock):** live payment behavior requires provider configuration and webhook setup; mock/local behavior may exist in non-production paths—verify per environment.
- **Uploads/verification storage:** depends on storage backend configuration.
- **Email:** depends on provider configuration.

Mark any unverified production behavior as environment-specific rather than assuming it from local code paths.
