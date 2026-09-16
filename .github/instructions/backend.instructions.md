---
applyTo: "app/**/*.py,tests/**/*.py,migrations/**/*.py,scripts/**/*.py"
---

Review backend changes against these risks:

- State transitions must reject invalid source states and preserve explicit copy and asset
  approval gates.
- Multi-row changes must remain atomic. Check rollback behavior, idempotency-key reuse, worker
  wakeups, retries, cancellation races, stale-worker recovery, and duplicate processing.
- Migration changes must upgrade both empty and supported legacy databases without data loss.
- Upload filenames, MIME signatures, sizes, and resolved paths must remain constrained; public
  responses must not expose absolute paths, credentials, or raw provider errors.
- Automated tests must use mock providers and isolated temporary storage.

Require a focused regression test when a behavior, state transition, persistence rule, security
boundary, or recovery path changes.
