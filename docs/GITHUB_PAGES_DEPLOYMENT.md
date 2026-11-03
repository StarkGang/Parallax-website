# GitHub Pages deployment

The Actions workflow installs with `npm ci`, builds Vite, uploads `dist`, and deploys through Pages. It runs on `main` pushes and manual dispatch with least-needed Pages permissions. Project sites receive `/<repository>/` from the repository name; set the repository variable `VITE_BASE_PATH=/` for a user site/custom domain. Local builds default to `./`.

Enable Pages via **Settings → Pages → Build and deployment → GitHub Actions**. Push to `main`, wait for the Actions deployment, and open the published URL in the job summary. Do not claim deployment until this is completed by the repository owner.

HashRouter avoids server rewrite requirements. A blank page: inspect browser console/network, verify Vite asset URLs begin with the project prefix, and ensure the variable includes opening and trailing slash. If testing locally with the repository prefix, run `VITE_BASE_PATH=/repo/ npm run build` then preview from a server path matching that base. Set `/` on custom domains and configure the domain in Pages separately.
