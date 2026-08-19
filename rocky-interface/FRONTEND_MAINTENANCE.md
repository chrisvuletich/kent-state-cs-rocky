# Rocky Frontend Maintenance Guide

This guide is the short architectural handoff for students and interns changing
`rocky-interface`. Read the main `README.md` first for setup, authentication,
streaming, and image-input behavior.

## The frontend in one minute

- SvelteKit renders one authenticated workspace at `/`.
- The URL selects the active frame and any selected course, conversation, help
  document, or analytics filters.
- SvelteKit server routes proxy authenticated requests to the Flask backend.
- The backend remains the authority for permissions and stored data. Hiding a
  control in the frontend is not an authorization check.
- Foundation and shared route CSS load once from the root layout. A component
  imports the stylesheet that specifically owns that component.
- Vitest protects pure TypeScript and component contracts. The existing
  Selenium harness protects behavior that needs a real browser.

## URL and frame state

Treat the URL as the only active navigation state:

```text
/?frame=dashboard
/?frame=courses&course=3
/?frame=chat&conversation=<conversation-id>
/?frame=help&doc=<document-id>
/?frame=analytics&range=24h&dimension=user
```

The `rocky_current_frame` cookie is only a short-lived fallback for a visit to
`/` without `frame`. Do not add another active-frame copy in a Svelte store or
browser storage.

Use these sources of truth:

- `src/lib/types/frame.ts`: frame names, labels, and role-visible frame lists.
- `src/lib/navigation/frameRegistry.ts`: frame components and document titles.
- `src/lib/navigation/appRoute.ts`: URL construction, query ownership, parsing,
  and safe frame resolution.
- `src/routes/+layout.server.ts`: server-side validation, remembered-frame
  fallback, and the initial rendered frame.
- `src/routes/+page.svelte`: renders the component selected by the resolved
  frame.

Use `appHref()` for links and `buildAppUrl()` when an action must finish before
navigating. Prefer real links for navigation so reload, copy/paste, browser
history, open-in-new-tab, and keyboard behavior work without extra code. Each
frame owns the query keys listed for it in `appFrameQueryKeys`; changing frames
must not leak another frame's selection or filters.

### Adding a frame

1. Create the view under `src/lib/components/views` with one clear `<h1>`.
2. Add its name and label to `src/lib/types/frame.ts`.
3. Put it in the correct role lists in that file. This controls navigation and
   initial frame resolution, but backend authorization is still required for
   protected data.
4. Register the component and page title in
   `src/lib/navigation/frameRegistry.ts`.
5. Add its icon to `frameIcons` in `src/lib/components/Sidebar.svelte`.
6. Add only its owned URL parameters to `appFrameQueryKeys`.
7. Add a canonical-navigation assertion to the existing navigation browser
   test and a direct-load/unauthorized case when the frame is restricted.

Do not set frame state directly from a component. Add a link or build a URL
through the navigation helper.

## Dialogs, drawers, and disclosures

`src/lib/actions/focusScope.ts` is the small shared behavior for true modal
surfaces. Use it for dialogs and mobile drawers that must:

- move focus inside when opened;
- keep Tab and Shift+Tab inside;
- make the background inert;
- close through the supplied Escape callback; and
- return focus to a persistent opener.

Give a modal surface `role="dialog"` (or native `<dialog>`), an accessible name,
and `aria-modal="true"`. Pass an explicit `returnFocusTo` when the control that
triggered the action is removed while the dialog is open.

Do not use `focusScope` for small non-modal disclosures. A disclosure needs an
`aria-expanded` trigger, `aria-controls`, Escape and outside-click dismissal,
and predictable focus. Prefer ordinary links, buttons, radio controls, and
selects over custom ARIA widgets.

## Responsive behavior

The regression anchors are defined as `UI_VIEWPORTS` in
`run-test/frontend/test_support.py`:

- 1440 × 1000 desktop
- 1024 × 600 short laptop
- 844 × 390 landscape phone
- 390 × 844 phone
- 320 × 568 narrow phone

They are test anchors, not breakpoint requirements. Keep layouts fluid between
them.

For every changed view:

- keep document-level horizontal overflow at zero;
- let wide tables scroll inside a labeled, keyboard-focusable region;
- keep the mobile top bar and all navigation destinations reachable;
- use `100dvh`, shrinkable flex children, and local scrolling for
  height-constrained surfaces;
- keep dialog actions reachable without zooming; and
- check long names, emails, identifiers, empty states, and error messages.

## Theme, color, fonts, and motion

Theme tokens live in `src/lib/styles/foundation/tokens.css`. Use semantic text,
background, border, and status tokens instead of adding a light-theme hex value
inside a component. Define both light and dark values when a new semantic token
needs different contrast.

- Normal text should reach a 4.5:1 contrast ratio.
- Focus indicators and meaningful non-text boundaries should reach 3:1 against
  adjacent colors.
- Solid button backgrounds and link text are separate semantic jobs; changing
  one global blue for both can fix one contrast problem and create another.
- The base and monospace font stacks are local system stacks. Do not introduce
  a runtime font CDN dependency.
- Use the transition-duration tokens. Global reduced-motion behavior lives in
  `src/lib/styles/foundation/motion.css`; a component should add a specific
  reduced-motion rule when merely shortening its animation could leave content
  translated, clipped, or hidden.

## Data, failure, and retained-content states

Every data-backed view should distinguish loading, empty, populated, and error
states. When refresh fails, keep the last trustworthy content visible when it
is still useful and provide Retry when recovery is meaningful. Disabled actions
must explain why they are disabled.

Do not weaken Rocky's institutional retention notice or audit behavior. Prompts,
attached images, responses, partial streaming output, administrative changes,
and relevant usage metadata remain subject to university logging and review.

## CSS ownership

- `src/lib/styles/foundation`: tokens, base elements, and global motion.
- `src/lib/styles/layout`: application shell and reusable layout primitives.
- `src/lib/styles/routes`: frame- or route-level composition.
- `src/lib/styles/components/modules`: a component family's canonical styles.

Before adding a selector, search for it. Extend its current owner instead of
creating a second definition or importing the same stylesheet from the root and
a component. `src/lib/styles/styleOwnership.test.ts` protects the component
families that previously had duplicate owners.

## Required checks before merging UI changes

From the repository root, run:

```sh
python run-test/test_all.py
```

That command runs backend and Granite tests, frontend unit tests, Svelte type
and accessibility checks, formatting, a production build with safe testing
configuration, and the complete Selenium browser suite. Do not use
`--skip-browser` for a release candidate.

Also exercise the changed flow manually:

1. Use keyboard-only navigation through the changed controls.
2. Check desktop and the most relevant mobile or short-height viewport.
3. Check light and dark themes when colors or surfaces changed.
4. Verify loading, empty, error, disabled, and populated states that apply.
5. Confirm there is no framework overlay, relevant console error, focus loss,
   or document-level horizontal overflow.
6. Add a regression test when navigation, focus, layout, browser history, or an
   async failure could silently break again.

The compact release matrix and the owner of each browser test live in
`run-test/UI_UX_ACCEPTANCE.md` and `run-test/README.md`.

## Common mistakes to avoid

- Duplicating the active frame in a store or local storage.
- Building a URL by hand and carrying stale `course`, `conversation`, `doc`, or
  analytics parameters into another frame.
- Treating hidden UI as authorization.
- Returning focus to an element that is removed when a disclosure closes.
- Adding incomplete `menu`, `tab`, or dialog ARIA semantics without their
  keyboard behavior.
- Making the document scroll sideways to accommodate a table.
- Replacing useful cached content with a blank error screen after refresh.
- Adding a new CSS definition because the existing owning module was not
  searched first.
- Running only a production build; rendered browser behavior is part of the
  release gate.
