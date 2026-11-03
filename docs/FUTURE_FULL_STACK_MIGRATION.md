# Future full-stack migration

Keep the React/Vite frontend and replace mock adapters with a typed/documented API client for a Node.js/Express REST API. Supabase Auth will provide Google OAuth in production; keep credentials and callback configuration outside public source. PostgreSQL should model convention editions, events, passes, registrations, teams, payments, eligibility, tickets, check-in, announcements, coordinators, roles and audit logs.

Suggested service boundaries: event list/detail; participant profile/verification; registration create/list/cancel; pricing/pass and included/add-on calculations; payment order/status; management event CRUD, coordinator assignment and reporting. Payment orders must be created server-side and status established through verified webhooks. Do not trust client-calculated totals.

Use database transactions and constraints for event capacity, pass requirement, included value cap/count, duplicate prevention and team membership. Enforce role and event-scoped coordinator permissions server-side. Add request validation, rate limits, privacy retention policy, audit logs, error/loading UI, monitoring and security review before real use. Never ship service-role keys, payment secrets or OAuth client secrets to the browser.
