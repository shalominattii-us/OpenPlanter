# Universal Opportunity Domain

This module adds a canonical, source-agnostic domain layer beneath OpenPlanter's existing daily Universal Opportunity Intake reports.

The daily intake and narrative report remain the production surface. The new layer allows the same normalized records and analysis already used by the report to be emitted as immutable, versioned, machine-readable artifacts.

## Pipeline

```text
Existing source ingestion
        ↓
Existing source normalization
        ↓
UniversalIntakeAdapter
        ├── Opportunity
        ├── EvidencePacket
        └── MissionCandidate
        ↓
Existing daily report and future execution systems
```

## Opportunity

`Opportunity` is the immutable normalized source record. Its stable identifier is derived from the source name plus the source's own identifier, falling back to the title when no external identifier exists.

A source amendment or synchronization update must create a new `Opportunity.version`; existing versions are not mutated.

Required invariants:

- stable `opportunity_id`
- version greater than or equal to one
- timezone-aware provenance retrieval timestamp
- non-negative financial values
- minimum amount not greater than maximum amount

## EvidencePacket

`EvidencePacket` records the structured analysis that previously appeared only as report prose. It references exactly one Opportunity version and contains independent assessment dimensions.

The initial adapter preserves the daily intake's current semantics for:

- strategic fit
- urgency
- complexity
- financial value and revenue path
- eligibility
- recommendations and flags

Each assessment carries a normalized score, confidence, rationale and structured facts. The packet is immutable and versioned.

## MissionCandidate

`MissionCandidate` records the deterministic qualification result for one Opportunity and one EvidencePacket version.

The initial policy uses explicit weights and thresholds. It does not make governance or execution decisions. Its only responsibility is to classify the opportunity as:

- `qualified`
- `review`
- `rejected`

Every decision stores the rule version, final score and component reasons so the result can be reproduced and audited.

## Incremental integration

The current daily report should remain unchanged while integration proceeds:

1. Pass each existing normalized intake mapping to `UniversalIntakeAdapter`.
2. Persist or emit the resulting Opportunity, EvidencePacket and MissionCandidate beside the existing report.
3. Compare the structured values with the rendered narrative.
4. Move report rendering onto the structured artifacts only after output parity is established.

Example:

```python
from agent.opportunities import (
    UniversalIntakeAdapter,
    build_mission_candidate,
    to_primitive,
)

adapter = UniversalIntakeAdapter(
    source_name="Grants.gov",
    source_url="https://www.grants.gov/",
)

opportunity = adapter.opportunity_from_record(normalized_record)
evidence_packet = adapter.evidence_from_record(opportunity, normalized_record)
mission_candidate = build_mission_candidate(opportunity, evidence_packet)

structured_output = {
    "opportunity": to_primitive(opportunity),
    "evidence_packet": to_primitive(evidence_packet),
    "mission_candidate": to_primitive(mission_candidate),
}
```

## Scope

This is a **Universal Opportunity Intake** domain model. It is not limited to governmental procurement or grants. The source, jurisdiction, opportunity type, currency, eligibility and metadata fields are deliberately generic so the same contract can represent:

- grants and cooperative agreements
- procurement opportunities
- SBIR/STTR topics
- research and innovation programs
- licensing and commercialization opportunities
- accelerators, foundations and corporate open-innovation calls
- state, municipal, Tribal and international opportunities
