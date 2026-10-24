# Phase 1 — Frontend foundation and premium UX

## Objective
Deliver a cohesive, accessible PesaGuard emerald glass interface without changing backend behavior accidentally.

## Tasks
- Inspect all routes and existing CSS import order before edits.
- Reuse official PesaGuard logo and favicon assets; do not redraw or invent replacement branding.
- Consolidate design tokens for dark emerald canvas, translucent surfaces, blur, border, focus, spacing, typography, radii, shadows, and motion.
- Apply shared components/styles to navigation, page headers, cards, forms, tables, dialogs, banners, alerts, status pills, pagination, search, and sign-in.
- Preserve legibility: glass effects must not lower text contrast or hide focus states; reduce blur/transparency on constrained devices.
- Verify loading, empty, error, retry, success, disabled, permission-denied, and no-results states.
- Ensure every control has a real action and accessible name; remove or explicitly disable unsupported actions.
- Verify no live page presents preview/synthetic data as production data.
- Add component tests for high-risk interactions and responsive/accessibility smoke checks.
- Remove contradictory CSS and avoid brittle global selectors that accidentally style unrelated elements.

## Acceptance
- Frontend tests and production build pass.
- All known routes render without console errors in a browser check.
- Keyboard-only navigation, focus, reduced motion, contrast and mobile overflow are checked.
- No API/backend/security contract changes are hidden in the visual refactor.
- Report visual checks that could not be run.
