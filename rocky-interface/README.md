# Rocky Interface (Frontend Developer Guide)

This README is for developers working in the SvelteKit frontend under `rocky-interface`.

## What this project owns

- UI rendering and user interaction.
- Route and frame navigation.
- Frontend API client calls.
- Proxying requests through SvelteKit server routes to the Flask backend.

The frontend does not directly own private data. The backend is the source of truth.

## Prerequisites

- Node.js 20+
- npm

## Local setup

Install dependencies:

```sh
npm install
```

Create env file:

1. Copy `.env.example` to `.env`
2. Set at least:
   - `PUBLIC_APP_ENV=development`
   - `PUBLIC_API_BASE_URL=http://127.0.0.1:5001`
   - `PUBLIC_ENABLE_MICROSOFT_OAUTH=false`

Microsoft OAuth (optional in development, required in production):

- `PUBLIC_MICROSOFT_CLIENT_ID=<entra-app-client-id>`
- `PUBLIC_MICROSOFT_TENANT_ID=<kent-tenant-id>` (a specific tenant is required)
- `ROCKY_SESSION_SECRET=<independent-random-secret-at-least-32-characters>`
- `ROCKY_INTERNAL_PROXY_SECRET=<random-secret-at-least-32-characters-shared-with-backend>`

MSAL uses browser session storage. Rocky logout clears the signed application
session and Rocky's MSAL cache without globally signing the user out of other
Kent Microsoft applications.

Redirect callback behavior:

- Rocky always uses `{origin}/login` as the Microsoft callback URL.
- This callback must be registered by Entra app admins in the app registration redirect URI list.

Auth mode rules:

- development: preview auth by default, Microsoft OAuth only when `PUBLIC_ENABLE_MICROSOFT_OAUTH=true`
- testing: preview auth only
- production: Microsoft OAuth only

## Run frontend locally

```sh
npm run dev
```

Optional open in browser:

```sh
npm run dev -- --open
```

## Build and preview

```sh
npm run build
npm run preview
```

## Backend integration expectations

- Frontend should call local proxy routes under `src/routes/api/backend/[...path]/+server.ts`.
- Proxy adds authenticated user headers and the private internal proxy secret
  used by the backend to trust those headers.
- Web sessions contain a signed, expiring identity value; the browser cannot
  create or alter a valid session without `ROCKY_SESSION_SECRET`.
- Do not add direct local JSON data reads for protected data.

## Administrator analytics workspace

Administrators have an `Analytics` frame backed by the Flask Phase 2 telemetry
endpoints. It provides:

- selectable `15m`, `1h`, `6h`, `24h`, `7d`, and `30d` windows;
- request/token throughput, model timing, token throughput, outcomes, and latency;
- breakdowns by user, course, API key, group, model, source, and outcome;
- a filterable administrative review queue and complete stored
  request/response inspection;
- review controls for flags, structured reasons, workflow status, and notes;
- bounded Granite GPU, VRAM, temperature, CPU, and RAM history synchronized
  with model speed, latency, token load, and model-load duration;
- automatic 30-second refresh while the tab is visible, retaining the last good
  data when a refresh fails;
- responsive desktop and mobile layouts, with request detail presented as a
  mobile bottom sheet.

The selected window, breakdown dimension, request ID, outcome filter, and review
filter are reflected in the URL as `analytics_window`, `analytics_dimension`,
`analytics_request`, `analytics_outcome`, and `analytics_review`, so a reload
restores the same analytical view. These values contain identifiers and view
choices only; request content and review notes are never placed in the URL.

## Built-in chat cancellation

While Rocky is generating, the composer displays a Stop control. Stopping
aborts the browser request, keeps the student's prompt available for editing,
and ignores a late browser response. This is intentionally client-side only:
work that already reached Granite or Ollama may still finish and remains part
of the required institutional audit record.

## Key folders

- `src/lib/components`: reusable UI components.
- `src/lib/components/views`: frame-level views (dashboard, courses, users, analytics, etc.).
- `src/lib/api`: frontend API wrappers.
- `src/routes`: page routes and API proxy routes.
- `src/lib/stores`: app state stores.

## Role behavior to preserve

- Admin: can access all frames and manage users/analytics/courses.
- Non-admin: limited frames and course access based on backend-authorized data.

When changing UI behavior, keep backend-enforced permissions as the final authority.
