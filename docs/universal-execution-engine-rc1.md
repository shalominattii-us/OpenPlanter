# Universal Execution Engine RC1

## Scope

This release candidate packages the deterministic opportunity execution engine as a reusable operator product. It includes durable SQLite state, immutable execution context snapshots, capability-routed plugins, controlled artifact materialization, explicit approval gates, a public CLI, and a complete local field-trial harness.

## Safety boundary

The included submission executor uses a local receipt transport. It does not send email, call an external API, upload to a portal, or make a contractual commitment. Real transports must remain separately configured and explicitly approved.

## Operator commands

Install from the repository:

```bash
python -m pip install .
```

Run the complete deterministic field trial:

```bash
openplanter-field-trial \
  --workspace var/opportunities/field-trial-001 \
  --actor operator-name
```

Operate an individual durable execution:

```bash
openplanter-execute init --database execution.sqlite3 --input opportunity.json
openplanter-execute status --database execution.sqlite3 --run-id <RUN_ID>
openplanter-execute advance --database execution.sqlite3 --run-id <RUN_ID> --max-steps 10
openplanter-execute approve --database execution.sqlite3 --run-id <RUN_ID> --step-id <STEP_ID> --actor approver-name
```

## Container

```bash
docker build -f Dockerfile.execution -t openplanter-execution-engine:rc1 .
docker run --rm openplanter-execution-engine:rc1 --help
```

Persist the ledger and artifacts by mounting `/data`:

```bash
docker run --rm \
  -v "$PWD/var/opportunities:/data" \
  openplanter-execution-engine:rc1 \
  status --database /data/execution.sqlite3 --run-id <RUN_ID>
```

## Release gate

The RC workflow must pass all of the following:

1. The complete execution-engine test suite.
2. A packaged CLI field trial producing exactly 12 artifacts.
3. Python wheel construction.
4. Container build and command smoke test.

## Known limitation

RC1 proves a complete, approval-gated local lifecycle. Production external submission still requires a separately reviewed transport adapter, credentials, idempotency controls, and channel-specific receipt verification.
