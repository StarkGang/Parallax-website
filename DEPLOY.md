# Parallax 2026 · Production Deployment Guide

This document provides a production-grade deployment runbook for **Parallax 2026** (FastAPI backend + Vite/React frontend + PostgreSQL database + S3/Supabase storage).

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Complete Environment Variables Inventory](#2-complete-environment-variables-inventory)
3. [Step-by-Step Secrets Retrieval Guide](#3-step-by-step-secrets-retrieval-guide)
   - [A. Secret Key (`SERVER_SECRET_KEY`)](#a-secret-key-server_secret_key)
   - [B. Database Connection (`DATABASE_URL`)](#b-database-connection-database_url)
   - [C. Google OAuth Credentials](#c-google-oauth-credentials)
   - [D. Razorpay Payment Gateway & Webhooks](#d-razorpay-payment-gateway--webhooks)
   - [E. Storage Backend (Supabase or AWS S3)](#e-storage-backend-supabase-or-aws-s3)
   - [F. Transactional Email Server (SMTP)](#f-transactional-email-server-smtp)
4. [Deployment Runbooks](#4-deployment-runbooks)
   - [Runbook 1: Vercel (Frontend) + Render / Railway (Backend) + Supabase (Recommended)](#runbook-1-vercel-frontend--render--railway-backend--supabase-recommended)
   - [Runbook 2: Docker Compose on a Single Linux VPS (DigitalOcean / Hetzner / AWS EC2)](#runbook-2-docker-compose-on-a-single-linux-vps)
5. [Database Initialization & Seeding](#5-database-initialization--seeding)
6. [Post-Deployment Verification & Health Checks](#6-post-deployment-verification--health-checks)

---

## 1. Architecture Overview

Parallax is separated into two components designed for horizontal scalability:

```
[ Participant / Admin Browser ]
              │
       HTTPS Requests
              ▼
   ┌──────────────────────┐         ┌─────────────────────────────────────┐
   │ Frontend SPA         │         │ FastAPI Backend API                 │
   │ (Vercel / Netlify /  │ ──────> │ (Render / Railway / Fly.io / VPS)   │
   │ Cloudflare Pages)    │  proxy  │ Port: 8000                          │
   └──────────────────────┘         └──────────────────┬──────────────────┘
                                                       │
                           ┌───────────────────────────┼───────────────────────────┐
                           ▼                           ▼                           ▼
                 ┌───────────────────┐       ┌───────────────────┐       ┌───────────────────┐
                 │ PostgreSQL 15+    │       │ Cloud Storage     │       │ External Services │
                 │ (Supabase / Neon) │       │ (Supabase / S3)   │       │ Razorpay, Google, │
                 │ Transactions & DB │       │ Passports & IDs   │       │ SMTP Mail Server  │
                 └───────────────────┘       └───────────────────┘       └───────────────────┘
```

---

## 2. Complete Environment Variables Inventory

### Backend Environment Variables (`backend/.env`)

| Variable | Required in Prod? | Default (Dev) | Description |
|---|---|---|---|
| `APP_ENV` | **YES** | `development` | Set to `production` in live environments. Enforces HTTPS cookies, security headers, and disables Swagger UI if needed. |
| `APP_DEBUG` | **NO** | `false` | Enable verbose tracebacks. Must be `false` in production. |
| `SERVER_SECRET_KEY` | **YES** | - | 64-character hex key used to sign sessions, ticket HMACs, and CSRF tokens. |
| `APP_BASE_URL` | **YES** | `http://localhost:8000` | Canonical public URL of your backend (e.g., `https://api.parallax.nssce.ac.in`). Used for OAuth redirect URI construction. |
| `FRONTEND_ORIGIN` | **YES** | `http://localhost:5173` | Canonical public origin of your frontend SPA (e.g., `https://parallax.nssce.ac.in`). Used for CORS and strict CSRF origin validation. |
| `ALLOWED_HOSTS` | **YES** | `localhost,127.0.0.1` | Comma-separated list of host headers permitted by TrustedHost middleware (e.g., `api.parallax.nssce.ac.in,parallax.nssce.ac.in`). |
| `DATABASE_URL` | **YES** | `sqlite+aiosqlite:///./var/parallax.db` | PostgreSQL async connection string: `postgresql+asyncpg://user:pass@host:5432/dbname`. |
| `COOKIE_SECURE` | **YES** | `false` | Set to `true` in production to enforce `Secure; HttpOnly; SameSite=Lax` cookies over HTTPS. |
| `BOOTSTRAP_OWNER_EMAIL` | **YES** | `owner@parallax.local` | Email address that automatically receives the `super_admin` role when they first sign in. |
| `GOOGLE_CLIENT_ID` | Optional | `""` | Google Cloud OAuth 2.0 Web Client ID. |
| `GOOGLE_CLIENT_SECRET` | Optional | `""` | Google Cloud OAuth 2.0 Client Secret. |
| `PAYMENTS_ENABLED` | **YES** | `false` | Set to `true` to enable Razorpay checkouts. Set to `false` for instant zero-friction sandbox pass activations. |
| `RAZORPAY_KEY_ID` | If Payments ON | `""` | Live Key ID from Razorpay Dashboard (`rzp_live_...` or `rzp_test_...`). |
| `RAZORPAY_KEY_SECRET` | If Payments ON | `""` | Live Key Secret from Razorpay Dashboard. |
| `RAZORPAY_WEBHOOK_SECRET` | If Payments ON | `""` | Webhook secret configured on Razorpay for event signature verification. |
| `STORAGE_BACKEND` | Optional | `auto` | `auto`, `local`, `supabase`, or `s3`. Defaults to `supabase` if Supabase keys exist, otherwise `local`. |
| `SUPABASE_URL` | If Supabase | `""` | `https://<project-ref>.supabase.co`. |
| `SUPABASE_KEY` | If Supabase | `""` | Supabase Anon public key. |
| `SUPABASE_SERVICE_ROLE_KEY` | If Supabase | `""` | Supabase Service Role Secret Key (bypasses RLS for secure server verification uploads). |
| `SUPABASE_STORAGE_BUCKET` | If Supabase | `parallax` | Storage bucket name in Supabase for student verification ID cards. |
| `SMTP_HOST` | Optional | `""` | Outgoing mail server (e.g. `smtp.resend.com` or `smtp.gmail.com`). |
| `SMTP_PORT` | Optional | `587` | Port (usually `587` for STARTTLS or `465` for SSL). |
| `SMTP_USERNAME` | Optional | `""` | Mail username. |
| `SMTP_PASSWORD` | Optional | `""` | Mail password / API key. |
| `SMTP_FROM_EMAIL` | Optional | `no-reply@parallax.nssce.ac.in` | Official sender email. |
| `DEV_AUTH_ENABLED` | **NO** | `true` | **MUST BE `false` IN PRODUCTION** to disable one-click simulated test accounts. |

### Frontend Environment Variables (`frontend/.env.production`)

| Variable | Required? | Default | Description |
|---|---|---|---|
| `VITE_API_BASE` | Optional | `/api/v1` | If frontend and backend are hosted on separate domains, set to `https://api.yourdomain.com/api/v1`. If behind a reverse proxy (Caddy/Nginx) or CDN rewrite, keep `/api/v1`. |

---

## 3. Step-by-Step Secrets Retrieval Guide

### A. Secret Key (`SERVER_SECRET_KEY`)
You need a cryptographically secure 256-bit secret key.
Generate one with Python in your terminal:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
*Output example*: `4d82b3a1f9e28c704e6732f1a9b2c3d4e5f60718293a4b5c6d7e8f901a2b3c4d`
Set this as `SERVER_SECRET_KEY`.

---

### B. Database Connection (`DATABASE_URL`)
Production requires PostgreSQL 15+. Free reliable providers include **Supabase**, **Neon.tech**, and **Render PostgreSQL**.

#### Option 1: Supabase (Recommended - Free Tier)
1. Go to [supabase.com](https://supabase.com) and create an account.
2. Click **New Project** → Name it `parallax-2026` → Set a strong database password.
3. Choose region **Mumbai / South Asia (`ap-south-1`)** for lowest latency to Kerala.
4. Once deployed, navigate to **Project Settings** (gear icon) → **Database**.
5. Under **Connection string**, select **URI**.
   - Copy the connection URI:
     `postgresql://postgres.[ref]:[PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:6543/postgres`
6. In `backend/.env`, format the protocol to asyncpg:
   Replace `postgresql://` with `postgresql+asyncpg://`:
   ```env
   DATABASE_URL=postgresql+asyncpg://postgres.yourref:YourPassword@aws-0-ap-south-1.pooler.supabase.com:6543/postgres
   ```

---

### C. Google OAuth Credentials
Google Sign-In provides seamless 1-click authentication without requiring users to create or remember passwords.

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project: `Parallax-Convention`.
3. In the sidebar, go to **APIs & Services** → **OAuth consent screen**:
   - User Type: **External**.
   - App Name: `Parallax 2026`.
   - User support email: Select your email.
   - Developer contact email: Select your email.
   - Click **Save and Continue**.
   - Under **Scopes**, click **Add or Remove Scopes** and select:
     - `.../auth/userinfo.email`
     - `.../auth/userinfo.profile`
     - `openid`
   - Complete the wizard.
4. In the sidebar, click **Credentials** → **Create Credentials** → **OAuth client ID**:
   - Application type: **Web application**.
   - Name: `Parallax Web Production`.
   - **Authorized JavaScript origins**:
     - `https://parallax.nssce.ac.in` (your production frontend URL)
   - **Authorized redirect URIs**:
     - `https://api.parallax.nssce.ac.in/api/v1/auth/google/callback` (your backend callback URL)
     - `http://localhost:8000/api/v1/auth/google/callback` (for local development testing)
5. Click **Create**. A dialog will display:
   - **Client ID** (e.g. `123456789-abcdef.apps.googleusercontent.com`)
   - **Client Secret** (e.g. `GOCSPX-xxxxxxxxxxxxxx`)
6. Add them to `backend/.env`:
   ```env
   GOOGLE_CLIENT_ID=123456789-abcdef.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxx
   ```

---

### D. Razorpay Payment Gateway & Webhooks
Razorpay handles registration fee collections, convention passes, and UPI/Card payments.

1. Log in to [dashboard.razorpay.com](https://dashboard.razorpay.com).
2. Complete KYC if you want to collect real funds (Live mode) or use **Test Mode** for testing.
3. Go to **Settings** → **API Keys** → Click **Generate Key**:
   - Copy **Key ID** (`rzp_live_...` or `rzp_test_...`)
   - Copy **Key Secret**
4. Configure Webhooks (Critical for asynchronous payment confirmation):
   - Go to **Settings** → **Webhooks** → Click **Add New Webhook**.
   - Webhook URL: `https://api.parallax.nssce.ac.in/api/v1/webhooks/razorpay`
   - Secret: Type any strong random secret (e.g., `whsec_parallax2026_live_abc123`).
   - Active Events: Select:
     - `order.paid`
     - `payment.captured`
     - `payment.failed`
   - Click **Save**.
5. Add them to `backend/.env`:
   ```env
   PAYMENTS_ENABLED=true
   RAZORPAY_KEY_ID=rzp_live_xxxxxxxx
   RAZORPAY_KEY_SECRET=yyyyyyyyyyyyyy
   RAZORPAY_WEBHOOK_SECRET=whsec_parallax2026_live_abc123
   ```

> **Note**: If you do not want payment processing yet, leave `PAYMENTS_ENABLED=false`. The system will automatically use sandbox order activation where passes and event selections activate instantly.

---

### E. Storage Backend (Supabase or AWS S3)
The convention platform stores student ID cards and institutional proof documents for verification.

#### Using Supabase Storage (Free Tier)
1. In your Supabase Dashboard, go to **Storage**.
2. Click **Create new bucket**:
   - Name: `parallax`
   - Public bucket: **OFF** (Keep private to protect student identity documents).
3. Go to **Project Settings** → **API**:
   - Copy **Project URL** (`https://xyz.supabase.co`)
   - Copy **anon public** key
   - Copy **service_role secret** key (Reveal secret)
4. Add them to `backend/.env`:
   ```env
   STORAGE_BACKEND=supabase
   SUPABASE_URL=https://xyz.supabase.co
   SUPABASE_KEY=eyJhbGci...anon...
   SUPABASE_SERVICE_ROLE_KEY=eyJhbGci...service_role...
   SUPABASE_STORAGE_BUCKET=parallax
   ```

---

### F. Transactional Email Server (SMTP)
Email is used for ticket confirmation, QR passes, and administrative password resets.

#### Free Option 1: Resend (Recommended, 3,000 free emails/month)
1. Sign up at [resend.com](https://resend.com).
2. Go to **Domains** → Add your domain (e.g. `nssce.ac.in` or `parallax.nssce.ac.in`) and add the DNS TXT records.
3. Go to **API Keys** → Click **Create API Key**.
4. Configure SMTP settings in `backend/.env`:
   ```env
   SMTP_HOST=smtp.resend.com
   SMTP_PORT=587
   SMTP_USERNAME=resend
   SMTP_PASSWORD=re_123456789_abcdef
   SMTP_FROM_EMAIL=tickets@parallax.nssce.ac.in
   ```

#### Free Option 2: Brevo / Sendinblue (300 free emails/day)
```env
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USERNAME=your-account-email@gmail.com
SMTP_PASSWORD=your-smtp-master-key
SMTP_FROM_EMAIL=iste@nssce.ac.in
```

---

## 4. Deployment Runbooks

### Runbook 1: Vercel (Frontend) + Render / Railway (Backend) + Supabase (Recommended)

This is the standard modern serverless/PaaS setup requiring zero server maintenance.

#### 1. Backend on Render.com
1. Push your repository to GitHub.
2. In Render Dashboard, click **New** → **Web Service**.
3. Connect your GitHub repository.
4. Settings:
   - **Name**: `parallax-api`
   - **Region**: Singapore or Frankfurt
   - **Root Directory**: `backend`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port 10000 --workers 4`
5. Click **Advanced** → **Add Environment Variable**:
   - Add all variables from Section 2 (`APP_ENV=production`, `SERVER_SECRET_KEY`, `DATABASE_URL`, `FRONTEND_ORIGIN`, etc.).
6. Click **Create Web Service**. Note your backend URL (e.g., `https://parallax-api.onrender.com`).

#### 2. Frontend on Vercel
1. Go to [vercel.com](https://vercel.com) → Click **Add New** → **Project**.
2. Select your repository.
3. Configure Project:
   - **Framework Preset**: `Vite`
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
4. In **Environment Variables**, add:
   - `VITE_API_BASE`: `https://parallax-api.onrender.com/api/v1`
5. Click **Deploy**.
6. Set your custom domain in Vercel (e.g., `parallax.nssce.ac.in`).
7. Update `FRONTEND_ORIGIN` in your Render backend settings to match your live Vercel URL!

---

### Runbook 2: Docker Compose on a Single Linux VPS

For complete data sovereignty, you can host both frontend, backend, and reverse proxy on a single Ubuntu VPS ($5 - $10/mo on Hetzner, DigitalOcean, or AWS EC2).

Create a `docker-compose.prod.yml` in your workspace root:

```yaml
version: '3.8'

services:
  db:
    image: postgres:16-alpine
    restart: always
    environment:
      POSTGRES_DB: parallax
      POSTGRES_USER: parallax_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U parallax_user -d parallax"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    restart: always
    depends_on:
      db:
        condition: service_healthy
    environment:
      - APP_ENV=production
      - APP_DEBUG=false
      - SERVER_SECRET_KEY=${SERVER_SECRET_KEY}
      - DATABASE_URL=postgresql+asyncpg://parallax_user:${DB_PASSWORD}@db:5432/parallax
      - FRONTEND_ORIGIN=https://${DOMAIN}
      - APP_BASE_URL=https://${DOMAIN}
      - ALLOWED_HOSTS=${DOMAIN}
      - COOKIE_SECURE=true
      - PAYMENTS_ENABLED=${PAYMENTS_ENABLED:-false}
      - BOOTSTRAP_OWNER_EMAIL=${BOOTSTRAP_OWNER_EMAIL}
      - DEV_AUTH_ENABLED=false
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    restart: always

  caddy:
    image: caddy:2-alpine
    restart: always
    ports:
      - "80:80"
      - "443:443"
    environment:
      - DOMAIN=${DOMAIN}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config

volumes:
  pgdata:
  caddy_data:
  caddy_config:
```

With `Caddyfile` (Caddy automatically fetches and renews free Let's Encrypt SSL/TLS certificates):

```caddyfile
{$DOMAIN} {
    # API endpoints
    handle /api/* {
        reverse_proxy backend:8000
    }

    # Health endpoints
    handle /health/* {
        reverse_proxy backend:8000
    }

    # Frontend SPA
    handle {
        reverse_proxy frontend:80
    }
}
```

Run with:
```bash
docker compose -f docker-compose.prod.yml up -d
```

---

## 5. Database Initialization & Seeding

When deploying for the first time against an empty PostgreSQL database:

1. Connect to your backend container or production environment.
2. Run database table creation:
   ```bash
   python -c "import asyncio; from app.db.base import Base; from app.db.session import get_engine; asyncio.run((lambda: get_engine().begin())())"
   ```
3. Seed the default edition, categories, and events:
   ```bash
   python -c "import asyncio; from app.db.session import session_scope; from app.seed import seed_if_empty; asyncio.run(seed_if_empty(session_scope()))"
   ```
4. **Owner Bootstrap**:
   Sign in using the email specified in `BOOTSTRAP_OWNER_EMAIL` (e.g., `iste@nssce.ac.in`). The system will automatically promote your account to `owner` and grant full management rights across the admin portal.

---

## 6. Post-Deployment Verification & Health Checks

Verify your deployment with the following checklist:

| Check | Expected Result | Command / URL |
|---|---|---|
| Liveness Probe | HTTP 200 `{"status": "ok"}` | `curl -i https://api.yourdomain.com/health/live` |
| Readiness Probe (DB Check) | HTTP 200 `{"status": "ok"}` | `curl -i https://api.yourdomain.com/health/ready` |
| Security Headers | Check `X-Content-Type-Options: nosniff`, `Content-Security-Policy` | `curl -I https://api.yourdomain.com/api/v1/public/config` |
| Public Edition Data | Returns `Parallax 2026` hosted by NSS College of Engineering | `curl https://api.yourdomain.com/api/v1/public/editions/current` |
| Public Events | Returns all 12 events across Day 1 & Day 2 | `curl https://api.yourdomain.com/api/v1/public/editions/parallax-2026/events` |
| Public Schedule | Returns Day 1 & Day 2 schedule items at NSSCE | `curl https://api.yourdomain.com/api/v1/public/editions/parallax-2026/schedule` |
| Google Maps on Venue | Loads NSS College of Engineering, Palakkad map embed | Navigate to `https://yourdomain.com/venue` |
| Make My Pass Badge | Renders vertical badge with scannable QR, tear-strip, and print button | Sign in and visit `https://yourdomain.com/portal/tickets` |

---

*Document version: 2.1.0 · Last verified for Parallax 2026 Production Release.*

