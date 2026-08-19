# UI/UX Acceptance Guide

This guide keeps Rocky's UI checks small, repeatable, and understandable for
student maintainers. It is a release checklist, not a separate design system or
an exhaustive browser-testing framework.

## Maintenance rules

- Reuse the existing Svelte components, CSS tokens, Vitest suite, and Selenium
  browser harness before adding another dependency.
- Add a browser test only when the behavior depends on navigation, layout,
  focus, browser history, or another feature that a unit test cannot exercise.
- Keep screenshots as review artifacts through `ROCKY_E2E_SCREENSHOT_DIR`;
  screenshots are not committed release assets.
- Every UI change must preserve authentication, account-deactivation checks,
  audit logging, chat retention, and administrative visibility.
- Keep the release suite green between phases. Add a regression test in the
  same phase that fixes the behavior it protects.

## Reference viewports

The authoritative dimensions live in `frontend/test_support.py` as
`UI_VIEWPORTS`.

| Name | Size | Purpose |
| --- | ---: | --- |
| Desktop | 1440 x 1000 | Normal student and administrator workspace |
| Short laptop | 1024 x 600 | Sidebar and footer behavior with limited height |
| Phone landscape | 844 x 390 | Limited-height mobile navigation |
| Phone | 390 x 844 | Primary mobile layout |
| Narrow phone | 320 x 568 | Wrapping, dialogs, and minimum-width behavior |

These sizes are regression anchors, not a list of supported devices. Layouts
must remain fluid between them.

## State matrix

| Surface | Required states |
| --- | --- |
| Student | Dashboard, courses, chat, account, help |
| Instructor | Owned courses, student keys, group keys, chat |
| Administrator | Dashboard, users, analytics, audit logs, API keys, health |
| Chat | Ready, streaming, stopped, unavailable, history failure, image input |
| Data views | Loading, empty, populated, recoverable error |
| Session | Signed out, active account, inactive account |
| Appearance | Light and dark themes |

Not every state needs its own browser test. Prefer unit tests for data
transformation and browser tests for the critical path through rendered UI.

## Phase gates

### Phase 0: Baseline and guardrails

- The dashboard renders at every reference viewport.
- The document has no horizontal overflow on the baseline dashboard.
- No framework error overlay or unexpected severe browser-console error appears.
- The existing release-gate commands remain authoritative.

### Phase 1: Navigation

- Dashboard course and conversation links open the requested record.
- Sidebar, Account, Help, Admin, and post-create navigation update the URL.
- Direct load, refresh, back, and forward preserve the selected view.
- Invalid and unauthorized deep links fail safely.

### Phase 2: Dialogs, drawers, and disclosures

- Focus enters the opened surface and returns to its opener.
- Escape closes the surface.
- Tab cannot move into inert background content.
- The mobile menu reports its expanded state.

### Phase 3: Responsive layout

- All navigation remains reachable at the short-laptop and landscape sizes.
- Tables scroll inside their region rather than widening the document.
- Analytics summaries wrap without clipping.

### Phase 4: Forms and semantics

- Inputs have labels and errors are associated with their fields.
- Tabs and sortable headers support the expected keyboard behavior.
- The active navigation destination is announced programmatically.

Regression coverage lives in `frontend/test_form_semantics_chromedriver.py`.

### Phase 5: Chat resilience

- Unavailable chat explains why sending is disabled and preserves the draft.
- Conversation-history failures offer Retry without discarding cached results.
- The institutional logging notice remains visible and readable.

Regression coverage lives in `frontend/test_chat_resilience_chromedriver.py`.

### Phase 6: Theme and inactive accounts

- Light and dark preferences persist after reload.
- Normal-size dark-theme text reaches 4.5:1 contrast.
- The inactive-account page offers a truthful login or logout action.

Regression coverage lives in `frontend/test_theme_and_inactive_chromedriver.py`.

### Phase 7: Request-path performance

- Unrelated API requests do not load user appearance settings.
- Authentication and inactive-account enforcement remain unchanged.

Regression coverage lives in `rocky-interface/src/hooks.server.test.ts` and
`rocky-interface/src/routes/layoutServer.test.ts`.

### Phase 8: CSS and motion

- Component styles have one clear owner.
- The chosen font is actually available or the system stack is explicit.
- Reduced-motion preferences remove decorative movement without hiding status.

Regression coverage lives in `rocky-interface/src/lib/styles/styleOwnership.test.ts`
and `frontend/test_css_motion_chromedriver.py`.

### Phase 9: Final regression and intern handoff

- The complete release gate passes without skipping browser tests.
- Student, instructor, and administrator journeys remain covered.
- Every reference viewport is exercised by the dashboard baseline, with focused
  responsive tests for tables, dialogs, navigation, analytics, and chat.
- Light/dark contrast, reduced motion, navigation history, keyboard semantics,
  focus restoration, streaming, image input, unavailable chat, and Retry remain
  covered by the compact browser suite.
- A maintainer can follow `rocky-interface/FRONTEND_MAINTENANCE.md` to add a
  frame, use the shared focus behavior, extend responsive styles and theme
  tokens, and run the required pre-merge checks.

The browser suite is the automated accessibility smoke pass. It verifies the
DOM accessibility contract and keyboard behavior; a human screen-reader pass
is still required before materially changing labels, announcements, reading
order, or landmark structure.

## Commands

From the repository root:

```sh
python run-test/test_all.py
```

For faster frontend-only work:

These commands expect `rocky-interface/.env` to be configured as described in
the frontend README. On a clean checkout, use `python run-test/test_all.py`
instead; the runner supplies the testing environment automatically.

```sh
cd rocky-interface
npm run test:unit
npm run check
npm run lint
npm run build
```

Run the Selenium browser suite from the repository root with:

```sh
PYTHONPATH=run-test:rocky-backend python -m unittest discover -s run-test/frontend -p "test_*.py" -v
```

## UI pull-request checklist

- [ ] The changed flow works with a keyboard.
- [ ] Desktop and the most relevant mobile viewport were checked.
- [ ] Loading, empty, failure, and disabled states remain understandable.
- [ ] There is no new document-level horizontal overflow.
- [ ] Light and dark themes remain readable.
- [ ] No relevant browser-console error or framework overlay appears.
- [ ] A regression test was added when the defect could recur silently.
- [ ] `python run-test/test_all.py` passes before release.
