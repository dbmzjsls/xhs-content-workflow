# Workbench state machine

The public run states are fixed. The local worker is the only automatic transition actor; selection, revision, approvals, retry, and cancel are explicit API actions.

| State | Meaning | Allowed next state/action |
| --- | --- | --- |
| `queued` | Text work is waiting | worker → `running`; cancel → `canceled` |
| `running` | Text phase is executing | success → `copy_review_required`; error → `failed`; cancel → `canceled` |
| `copy_review_required` | Human copy gate | select/revise stays at gate; approve → `image_queued` |
| `image_queued` | Image work is waiting | worker → `image_running`; cancel → `canceled` |
| `image_running` | Image phase is executing | success → `asset_review_required`; error → `failed`; cancel → `canceled` |
| `asset_review_required` | Human asset gate | approve/export → `completed` |
| `completed` | Immutable publication package is available | terminal |
| `failed` | A text, revision, or image phase failed | phase-aware retry |
| `canceled` | Operator canceled active work | terminal |

## Gate and retry steps

- A successful text phase publishes `status=copy_review_required` with `current_step=copy_review`.
- A failed revision records `failed_phase=revision`; retry returns to `copy_review_required` with `current_step=copy_review`.
- Copy approval moves to `image_queued`; the worker claims it as `image_running` and `current_step=image_generation`.
- An image-phase failure keeps `current_step=image_generation`, allowing the UI to retain the image/status panel while showing the failure and retry control.
- A successful image phase publishes `status=asset_review_required` with `current_step=asset_review`.
- Asset approval and export complete in one reviewed mutation.

## Failure, cancellation, and recovery invariants

- Illegal transitions return a conflict and do not partially mutate the run.
- Mutation idempotency records commit with the business action.
- Provider failures are durable and retain internal diagnostics while public errors redact filesystem paths.
- Cancel wins over late provider completion; canceled work cannot publish candidates or image rows.
- Startup recovery interrupts stale running attempts, records them as failed attempts, and requeues only the affected phase.
- Retry reuses completed durable phase output rather than repeating successful work.

The v1 state machine assumes one local process and one operator. Distributed claims, multi-user authorization, automatic publishing, and scraping are outside its contract.
