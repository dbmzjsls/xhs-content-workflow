# Workflow methodology

The workbench treats content production as an auditable sequence, not a single prompt. Each durable run begins with a structured Brief and stops at two human-controlled gates before it can complete.

## 1. Brief and deterministic routing

The Brief records topic, audience, product function, pain point, style preference, and optional owned uploads. Normalization and style routing turn that input into a narrative plan. The content library policy and examples are versioned files so candidate decisions can be reproduced and reviewed.

## 2. Candidate round

The pipeline generates exactly three angles:

1. pain-scene narrative
2. before/after contrast
3. discovery-based experience summary

Every candidate receives a hard-rule report and five soft-score dimensions. Hard rules cover publication eligibility such as length, brand naming, required tags, discovery-style integration, a concrete scene, and prohibited hard-sell language. A failing candidate is repaired once and remains ineligible if it still fails. Only a hard-rule-passing candidate can be selected or recommended.

The fixed regression suite in `evals/brief_cases.yaml` exercises writing, speaking, commuting, and tutorial Briefs. CI uses the deterministic mock provider and asserts every candidate passes hard rules. Soft scores help compare eligible candidates; they do not override a hard failure.

## 3. Copy review gate

At `copy_review_required`, the operator can compare all three candidates, select an eligible candidate, and request a concrete revision. Revisions create child drafts rather than overwriting history. Copy approval is an explicit, idempotent action and is allowed only when an eligible draft is selected.

## 4. Image workflow and asset review gate

Copy approval queues image work. The worker classifies image tasks, selects owned/library references, rewrites prompts, generates assets, and records a prompt contract check. That check validates prompt constraints only; it does not inspect generated image pixels. Filesystem paths stay internal; the API exposes owned resource URLs.

Reference-based prompt rewriting is deterministic template assembly from reference role, label, and selection reason. It does not inspect image contents, and no image bytes are sent to the image provider. An uploaded image is retained as a local asset record and contributes metadata only during generation; it does not make the result follow the upload's composition, colors, or UI. The original upload is not promised as part of the publication ZIP. The mock image provider creates an explicit placeholder preview without calling a paid provider. Existing audit records and written export packages are immutable historical snapshots; the current UI and new exports state this capability boundary without rewriting old data.

At `asset_review_required`, the operator is the image-quality gate and inspects the generated assets alongside the prompt contract report. Approval creates an atomic Markdown/JSON/ZIP publication package. It does not publish externally. OCR, dimensions, and file-validity checks may be added later as separate automated image checks.

## 5. Audit and reproducibility

Runs, phase attempts, candidate rounds, revisions, review actions, references, image assets, errors, timestamps, durations, and provider/model metadata are persisted. Idempotency keys prevent duplicate review mutations. Failed text, revision, and image phases have phase-aware retry behavior, and canceled provider work cannot publish late results.

The local E2E launcher always forces both providers to `mock` and confines its SQLite database, uploads, and exports to a fresh OS temporary directory. Real-model evaluation is manual, explicitly cost-acknowledged, and excluded from CI.
