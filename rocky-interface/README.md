# Rocky Interface (Frontend Developer Guide)

This README is for developers working in the SvelteKit frontend under `rocky-interface`.

After local setup, read [FRONTEND_MAINTENANCE.md](FRONTEND_MAINTENANCE.md) before
changing navigation, overlays, responsive layout, theme tokens, or shared CSS.
It is the concise intern handoff and pre-merge checklist.

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

## Navigation state

Rocky's workspace uses one root page with small URL parameters rather than a
separate route for every view. Treat the URL as the active navigation state:

- `frame` selects the view;
- `course`, `conversation`, and `doc` select a record within that view;
- the `rocky_current_frame` cookie is only a one-hour fallback when `frame` is
  absent, not a second source of active state.

Build internal workspace links with `src/lib/navigation/appRoute.ts`. This
keeps stale parameters from leaking between views and gives links consistent
reload, copy/paste, and browser-history behavior. Administrator-only frames
are still checked on the server and unauthorized links resolve to Dashboard.

## Administrator analytics workspace

Administrators have an `Analytics` frame backed by the Flask telemetry
endpoints. It provides:

- selectable `15m`, `1h`, `6h`, `24h`, `7d`, and `30d` windows;
- request/token throughput, model timing, token throughput, outcomes, latency,
  and rate-limit enforcement/failure counts;
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

The selected window, breakdown dimension, request ID, and request filters are
reflected in the URL using compact parameters such as `range`, `dimension`,
`request`, `outcome`, `error_type`, and `review`, so a reload restores the same
analytical view. These values contain identifiers and view choices only;
request content and review notes are never placed in the URL.

## Built-in chat streaming and cancellation

Set `ROCKY_ENABLE_STREAMING=true` here only after Granite and the Rocky chat API
have enabled streaming. The SvelteKit proxy then relays SSE without buffering,
and the chat renders one assistant response incrementally. With the flag false,
the established buffered JSON path remains active.

While Rocky is generating, the composer displays a Stop control. Stopping
aborts the browser stream and refreshes durable conversation history before a
new request can be sent. Work completed before cancellation and all partial
prompt/response data remain part of the required institutional audit record.

## Built-in chat image attachments

When Rocky and Granite both advertise image input with matching limits, the
chat automatically exposes an attachment control. Students can select, paste,
or drop local JPEG, PNG, and WebP images, preview and remove them, and send text
plus images or an image-only turn. The browser performs early count, byte, and
pixel checks for useful feedback; the Rocky and Granite services still perform
the authoritative validation before inference.

The SvelteKit proxy reconstructs the supported Responses API content blocks
and never fetches remote image URLs. Attached images are shown in optimistic
messages and in reopened owned conversation history. They are covered by the
same institutional logging notice as prompts and responses.

Production must set `BODY_SIZE_LIMIT=10M` in the frontend environment. The
adapter's 512 KiB default cannot carry the documented image budget after
Base64 encoding; 10 MiB matches the tracked Nginx ceiling while keeping request
bodies bounded.

The Help Center includes capability-driven API reference material plus
standalone Streaming and Image Input examples. These examples explain terminal
SSE errors, network chunk boundaries, image limits, and the institutional
logging policy. A backend documentation contract test prevents the former
text-only/no-streaming guidance from returning unnoticed.

The repository-level `python run-test/test_all.py` release gate includes the
frontend unit suite, type checks, formatter, production build, and browser
journeys alongside the backend and Granite suites.

## Key folders

- `src/lib/components`: reusable UI components.
- `src/lib/components/views`: frame-level views (dashboard, courses, users, analytics, etc.).
- `src/lib/actions`: small, reusable DOM behaviors such as modal focus management.
- `src/lib/api`: frontend API wrappers.
- `src/routes`: page routes and API proxy routes.
- `src/lib/stores`: temporary UI state such as open dialogs and sidebar state.

## Role behavior to preserve

- Admin: can access all frames and manage users/analytics/courses.
- Non-admin: limited frames and course access based on backend-authorized data.

When changing UI behavior, keep backend-enforced permissions as the final authority.

## Focus-managed surfaces

Use `focusScope` for true modal dialogs and mobile drawers. It moves focus into
the surface, keeps Tab inside, makes the background inert, closes through the
provided Escape callback, and restores the opener. Give the surface an
accessible label and set `aria-modal="true"`. Non-modal disclosures such as the
Dashboard view menu should keep their simpler local focus and Escape handling.
