# Ruby Payer-Action Automation Engine

## Overview

This is a deterministic reliability and orchestration engine for structured payer work items.

Upstream systems decide what payer action is needed and emit a work item. This engine loads that batch, reconciles it, chooses a valid channel, and executes the action through a payer connector. It records workflow state, audit events, and a run summary.

It is not an LLM agent. It does not make clinical decisions or billing-policy decisions.

## Run

```bash
python engine.py --kit <kit_directory> --out <output_directory>
```

Example:

```bash
python engine.py --kit starter_kit --out output
```

`--kit` is a directory containing the work items, payer matrix, action-channel map, schemas, and mock connectors. `--out` is where the engine writes its outputs. The engine uses the Python standard library. Install `jsonschema` if you want the supplied validator to check output shape as well as coverage.

## Validate

```bash
python starter_kit/validate_submission_replacement.py \
  --kit starter_kit \
  --out output
```

Against the supplied kit, the current implementation passes that validator: 36 input work items, 36 reported work items, schema-valid audit and summary outputs, exact coverage, and consistent states and dispositions. Those counts describe this kit, not hardcoded engine logic.

## Architecture

- `config.py` loads work items, the payer capability matrix, and the action-channel map.
- `domain.py` defines workflow states, connector results, work-item models, and runtime state.
- `reconciler.py` reconciles the full batch before dispatch: supersession, tenant-scoped idempotency dedupe, and same tenant/encounter/action dedupe.
- `policies.py` selects a channel, bounds retries, and paces API calls.
- `store.py` persists workflow state in SQLite.
- `gateways/base.py` is the payer connector interface.
- `gateways/mock.py` adapts the provided `MockPayerGateway`.
- `orchestrator.py` runs the execution lifecycle: retries, ambiguity verification, state transitions, human escalation, and audit generation.
- `audit.py` writes `audit_log.jsonl`.
- `summary.py` writes per-item `run_summary.json`.

## Reliability Decisions

### Full-batch reconciliation before dispatch

The engine loads the entire batch before any external call. A later work item can supersede an earlier one, and `available_at` is not required to match file order. Dispatching line by line would create side effects for work that should never run. Superseded and duplicate items are marked cancelled before any connector call.

### Tenant-scoped idempotency

Idempotency uniqueness is `(tenant, idempotency_key)`. The same raw key under two tenants is two different actions. Within one tenant, a repeated key is reconciled away before dispatch so it does not create a second side effect.

### Ambiguous submissions

`AMBIGUOUS` does not immediately trigger resubmission. The engine records `awaiting_external_response` and audits that result. For `corrected_claim_submission` and `appeal_submission`, it then calls `submission_status(tenant, idempotency_key)`. If the submission is on file, it is completed from that check. It is retried only when it cannot be confirmed and the retry policy still allows another attempt. Otherwise it is permanently failed.

On a later process start, an item already in `awaiting_external_response` is not blindly executed again.

### Durable state / restart safety

Workflow state is stored in SQLite. A restarted process skips items that are already terminal. Cancelled or superseded items are not written to the audit log again.

A new output directory starts the mock gateway with `fresh=True`. If the state database or payer ledgers already exist, the gateway starts with `fresh=False`, so payer-side memory is not truncated. Rerunning against the same output directory does not create duplicate external side effects. On the supplied kit, a second run stays at 9 side effects, 42 connector interactions, and 43 audit events, and the validator still passes.

If a submission was saved as `IN_PROGRESS` and the payer already has that tenant-scoped key on file, restart resolves it with `submission_status` instead of submitting again.

### Retry/backoff

The engine owns the attempt count and passes it to the connector. Retries are bounded by the configured retry policy. A retry is scheduled at a later simulated minute than the failed attempt; API pacing can push it later still if that minute is already full. No `sleep()` and no wall clock are used.

### API pacing

API calls are limited per payer and per simulated minute, using each payer's `api_throttle_per_min`. Each payer has its own counter. When a minute is at capacity, the next API call is assigned to a later simulated minute. Non-API channels are not rate-limited, but a retry of those calls still advances simulated time.

### Human escalation

Items that need a person end in one of two states:

- `needs_human_review` for missing channels, missing artifacts, conflicts, connector human review, and channel errors listed below
- `warm_handoff_ready` when the connector returns a warm handoff

Those outcomes set `human_required` and are written to the audit log when a connector result produces them.

### Auditability

Every workflow outcome in the audit trail is structured JSON. Audit timestamps are `case_as_of` plus the simulated minute for that event, not the work item's `created_at` and not wall-clock time. An ambiguous submission produces one ambiguity event in `awaiting_external_response`, then a separate verification event after `submission_status`.

## Outputs

```text
<output_directory>/
├── audit_log.jsonl
├── run_summary.json
├── external_side_effect_ledger.jsonl
├── connector_interaction_ledger.jsonl
└── work_item_state.db
```

`audit_log.jsonl` and `run_summary.json` are the required engine outputs. The two ledgers are written by the provided mock connector and are useful for verification. `work_item_state.db` is internal durable engine state.

## Assumptions

1. Channel preference follows the order in `action_channel_map.csv`. The engine chooses the first channel that is valid for the action and supported by the payer.
2. Retry attempts are bounded by the configured retry policy.
3. `human_minutes`: the supplied kit requires the metric but does not define actual human task durations. The implementation therefore uses one unit for each final work item requiring human intervention. This is not a real-world time estimate.
4. `CHANNEL_UNAVAILABLE` and `INVALID_CHANNEL_FOR_ACTION` are escalated to human review in this implementation.
5. The fixed supplied `case_as_of` clock is used instead of wall-clock time for workflow timing and audit timestamps.

## Design Boundaries

Intentionally out of scope:

- no frontend
- no LLM or agent decision-making
- no production payer APIs
- no hidden scenario-specific branching
- no hardcoded work-item IDs, payer names, or scenario tags
- no unnecessary framework or policy-interface abstraction

The contract says a work item whose deadline is before `case_as_of` is already past due, but it does not specify a disposition. This engine does not invent one.

## Extensibility

- `PayerGateway` is the connector boundary. A new payer implements that interface only, and `engine.py` is the one place that selects the adapter. Channel choice, retries, reconciliation, state, and audit stay in the engine. `gateways/availity.py` is only an empty placeholder; it is not a working integration.

- Make retry and backoff policies configurable per payer or action instead of relying on the current defaults.