# Sovereign Governance Authority Boundary

## Status

This document records the governance boundary that OpenPlanter must honor. It is an implementation constraint, not a replacement for the Sovereign OS constitutional corpus.

## Authority hierarchy

1. An application may observe, normalize, qualify, and formulate intent.
2. Commander Z may prepare or arbitrate the intent and operational context.
3. EagleCrat evaluates regulatory, policy, jurisdictional, and risk considerations.
4. EagleCrat may identify a federal-compliant route, an override-eligible route, defer, or deny.
5. EagleCrat's output is advisory or delegated governance. It is not the final source of sovereignty.
6. Sovereign OS is the final authorization boundary and may uphold, constrain, defer, deny, or override a subordinate governance result according to sovereign doctrine.
7. Authorized action must be committed to the Sovereign Ledger before execution.

## Mission acceptance route

```text
MissionCandidate
  -> GovernanceRequest
  -> Commander Z intent/context formation
  -> EagleCrat regulatory and policy advisory
  -> Sovereign OS authorization
  -> Sovereign Ledger commit
  -> Mission
```

A qualification score never creates a Mission. A score can support triage and evidence assembly only.

## Core mutation law

No application, capability, agent, qualification engine, EagleCrat advisory, or learning process may directly modify the cybernetic core.

Every proposed core mutation must:

1. be represented as an explicit governance request;
2. identify the affected constitutional or cybernetic component;
3. carry evidence, intent, risk, and provenance;
4. pass applicable EagleCrat policy and regulatory review;
5. receive explicit Sovereign OS authorization;
6. be committed to the Sovereign Ledger; and
7. remain replayable and auditable.

Absence of authorization is denial. Silence, a high score, prior approval of a similar action, or an EagleCrat advisory does not imply sovereign authorization.

## Separation of roles

- **Qualification Engine:** determines whether evidence supports further consideration.
- **EagleCrat:** evaluates compliance, policy paths, jurisdiction, constraints, and override eligibility.
- **Sovereign OS:** holds final authority over mission acceptance and constitutional or cybernetic-core mutation.
- **Sovereign Ledger:** records the authorized decision and preserves causality.
- **OpenPlanter:** submits governed requests and consumes authorized outcomes. It does not emulate sovereign authority.

## Implementation invariants

- No `Mission` may be instantiated without a valid `SovereignAuthorization`.
- An authorized decision must include a Sovereign Ledger commit reference.
- Core-mutation requests use a distinct gate from ordinary mission acceptance.
- Governance records use stable identifiers and preserve references to candidate, evidence, decision, advisory, authorization, and ledger commit.
- EagleCrat dispositions and Sovereign OS decisions remain separate fields and separate records.

## Survey notes

The reviewed architecture describes EagleCrat as a governance or regulatory engine that evaluates compliant and sovereign-override paths. Other reviewed law material places immutable prime directives, sovereignty and mutation law, authority hierarchy, event legality, mutation permissions, replay validity, and continuity legality above ordinary application logic. The resulting interpretation is that EagleCrat participates in governance but does not exhaust or equal Sovereign OS authority.

This document should be amended only through the same governed core-change route it describes when the authoritative constitutional corpus provides a more precise hierarchy or naming contract.
