---
applyTo: "frontend/src/**/*.ts,frontend/src/**/*.tsx,frontend/e2e/**/*.ts,frontend/*.ts,frontend/*.json"
---

Review frontend changes for agreement with FastAPI schemas and the documented workflow state
machine. Check loading, error, retry, cancellation, and review-gate states rather than only the
happy path. Preserve the local-only API boundary and do not introduce automatic publishing or
real-provider calls.

Require `npm run build` for TypeScript or build configuration changes and a focused Playwright
test for user-visible workflow behavior. Avoid comments about formatting already enforced by the
toolchain.
