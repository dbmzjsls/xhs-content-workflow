# Repository review checklist

Use this as a relevance filter, not a requirement to comment on every category.

## Workflow and persistence

- Do transitions verify the expected source state and keep copy/asset approval explicit?
- Are database writes, idempotency records, step history, and wakeups committed consistently?
- Can retries, cancellation, stale-worker recovery, or concurrent requests duplicate or erase work?
- Do migrations preserve supported legacy data and remain safe on an empty database?

## Security and privacy

- Are upload size, signature, extension, filename, ownership, and resolved-path checks preserved?
- Can API responses expose local paths, secrets, raw provider messages, or another run's assets?
- Does any change expose the unauthenticated local application beyond `127.0.0.1`?

## Providers and determinism

- Could a test, CI job, fallback, or default configuration call a real text/image provider?
- Are provider failures explicit rather than silently replaced with plausible mock output?
- Is paid evaluation still guarded by an intentional acknowledgement?

## API and UI

- Do response schemas, status values, download URLs, and frontend assumptions remain aligned?
- Are refresh, error, retry, cancel, and approval states covered in addition to the happy path?
- Does user-visible behavior have a focused pytest or Playwright regression test?
