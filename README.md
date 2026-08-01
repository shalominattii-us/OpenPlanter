# Foundry

## From opportunity to outcome.

Foundry is an autonomous execution platform for turning qualified opportunities into durable, reviewable outcomes.

Give Foundry an opportunity. It researches the problem, evaluates eligibility, designs a mutually beneficial offer, builds the response package, prepares outreach, stops at explicit approval boundaries, records submission evidence, and tracks the result.

Every execution is deterministic, inspectable, restart-safe, and artifact-producing.

## What Foundry Does

```text
Opportunity
    ↓
Evidence
    ↓
Qualification
    ↓
Execution Plan
    ↓
Research
    ↓
Eligibility
    ↓
Offer Design
    ↓
Deliverables
    ↓
Outreach Preparation
    ↓
Explicit Approval
    ↓
Submission Receipt
    ↓
Outcome Record
```

Foundry is designed for companies, government contractors, public institutions, teams, and individuals that need a governed path from discovery to execution.

## Core Principles

- **Execution over suggestion** — Foundry produces usable work and durable artifacts.
- **Human authority at consequential boundaries** — external action remains approval-gated.
- **Deterministic orchestration** — the engine owns state, ordering, retries, and completion.
- **Replayable evidence** — runs, events, artifacts, checksums, and outcomes are preserved.
- **Composable executors** — plugins perform bounded work without gaining orchestration authority.
- **Portable operation** — the same engine runs through Python, CLI, SQLite, and containers.

## Current Release Candidate

RC1 includes:

- canonical opportunity, evidence, qualification, plan, run, event, artifact, and outcome contracts
- deterministic execution service and bounded run loop
- durable SQLite execution ledger
- immutable context snapshots and restart-safe continuation
- research, eligibility, offer-design, deliverable, outreach, submission, and outcome executors
- atomic artifact materialization with SHA-256 verification
- operational CLI and end-to-end field-trial harness
- Python wheel, source distribution, and non-root Docker runtime

The RC1 submission transport is intentionally local and simulated. It requires explicit approval and produces an authoritative receipt, but it does not send email, call a portal, or submit to an external API.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Run the complete local field trial:

```bash
foundry-field-trial \
  --workspace var/foundry/field-trial-001 \
  --actor foundry-operator
```

Operate a durable execution directly:

```bash
foundry init --help
foundry status --help
foundry advance --help
foundry approve --help
```

## Durable Outputs

A completed execution produces a traceable set of artifacts, including:

- validated opportunity brief
- eligibility matrix
- offer design
- value model
- proposal draft
- implementation plan
- budget assumptions
- outreach draft
- submission checklist
- contact brief
- submission receipt
- outcome record

Each materialized artifact is recorded with its exact file URI, byte size, checksum, producing step, and execution lineage.

## Container

```bash
docker build -f Dockerfile.execution -t foundry-execution-engine:rc1 .
docker run --rm foundry-execution-engine:rc1 --help
```

Mount a durable workspace at `/data` for ledgers and artifacts.

## Compatibility

Foundry is the new product identity for OpenPlanter. Transitional `openplanter-*` CLI aliases remain available during the migration so existing scripts and deployments continue to work.

## Development

Run the execution-engine suite:

```bash
python -m pytest \
  tests/test_opportunity_execution.py \
  tests/test_execution_record.py \
  tests/test_execution_lifecycle.py \
  tests/test_execution_orchestrator.py \
  tests/test_plugin_runtime.py \
  tests/test_research_executor.py \
  tests/test_eligibility_executor.py \
  tests/test_runtime_result_integration.py \
  tests/test_deterministic_execution_service.py \
  tests/test_deterministic_run_loop.py \
  tests/test_sqlite_execution_store.py \
  tests/test_execution_context_snapshot.py \
  tests/test_execution_cli.py \
  tests/test_artifact_materialization.py \
  tests/test_offer_design_executor.py \
  tests/test_deliverable_builder_executor.py \
  tests/test_outreach_preparation_executor.py \
  tests/test_submission_executor.py \
  tests/test_outcome_tracking_executor.py \
  tests/test_execution_field_trial.py -q
```

## License

MIT — see [LICENSE](LICENSE).
