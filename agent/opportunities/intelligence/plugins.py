from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from .contracts import (
    CommercializationDecision,
    CommercializationStatus,
    IntelligenceStage,
    MaturityDecision,
    MaturityStage,
    SourceVerificationResult,
    StrategicIntelligenceScore,
    TemporalStatus,
    VerificationStatus,
)
from .plugin import OpportunityIntelligenceContext
from .policy import (
    load_commercialization_policy,
    load_intelligence_policy,
    sha256_json,
)


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def _round_one(value: float) -> float:
    return round(value + 1e-12, 1)


def _strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    try:
        return tuple(str(item) for item in value if str(item).strip())
    except TypeError:
        return (str(value),)


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return tuple(result)


def _is_authoritative_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _temporal_status(context: OpportunityIntelligenceContext) -> TemporalStatus:
    opportunity = context.opportunity
    status = opportunity.status.strip().lower()
    opportunity_type = opportunity.opportunity_type.strip().lower()
    metadata = opportunity.metadata
    classification = str(metadata.get("classification") or "").strip().lower()
    if "forecast" in status or "forecast" in opportunity_type or "forecast" in classification:
        return TemporalStatus.FORECAST
    if (
        "program" in classification
        or (
            "program" in opportunity_type
            and opportunity.deadline is None
            and opportunity.external_id is None
        )
    ):
        return TemporalStatus.PROGRAM_ONLY
    if status in {"closed", "inactive", "archived", "cancelled", "canceled", "historical"}:
        return TemporalStatus.CLOSED
    if opportunity.deadline is None:
        return TemporalStatus.UNKNOWN
    evaluation_date = context.evaluated_at.date()
    if opportunity.deadline < evaluation_date:
        return TemporalStatus.CLOSED
    if opportunity.deadline == evaluation_date:
        return TemporalStatus.DEADLINE_TODAY
    return TemporalStatus.OPEN


@dataclass(frozen=True)
class SourceVerificationPlugin:
    plugin_id: str = "cybercore-source-verification"
    version: str = "1.0.0"
    stage: IntelligenceStage = IntelligenceStage.SOURCE_VERIFICATION
    order: int = 1

    def execute(self, context: OpportunityIntelligenceContext) -> SourceVerificationResult:
        opportunity = context.opportunity
        metadata = opportunity.metadata
        source_urls = _unique(
            (
                *(item.source_url for item in context.evidence_packet.provenance),
                *_strings(metadata.get("source_urls")),
            )
        )
        source_authority = str(
            metadata.get("source_authority")
            or context.evidence_packet.provenance[0].source_name
        )
        identifier = opportunity.external_id or opportunity.provenance.source_record_id
        explicit_flags = any(
            key in metadata
            for key in ("issuer_verified", "identifier_verified", "deadline_verified")
        )
        checks = {
            "issuer": bool(opportunity.issuer and opportunity.issuer.strip())
            and (not explicit_flags or bool(metadata.get("issuer_verified"))),
            "identifier": bool(identifier and identifier.strip())
            and (not explicit_flags or bool(metadata.get("identifier_verified"))),
            "deadline": opportunity.deadline is not None
            and (not explicit_flags or bool(metadata.get("deadline_verified"))),
            "authoritative_source": bool(source_urls) and all(
                _is_authoritative_url(url) for url in source_urls
            ),
        }
        verified_fields = tuple(name for name, verified in checks.items() if verified)
        missing_fields = tuple(name for name, verified in checks.items() if not verified)
        status = (
            VerificationStatus.VERIFIED
            if not missing_fields
            else VerificationStatus.NEEDS_SOURCE_VERIFICATION
        )
        temporal = _temporal_status(context)
        evidence_payload = {
            "opportunity_id": opportunity.opportunity_id,
            "opportunity_version": opportunity.version,
            "issuer": opportunity.issuer,
            "identifier": identifier,
            "deadline": opportunity.deadline.isoformat() if opportunity.deadline else None,
            "source_authority": source_authority,
            "source_urls": source_urls,
            "retrieved_at": [item.retrieved_at.isoformat() for item in context.evidence_packet.provenance],
            "status": status.value,
            "temporal_status": temporal.value,
        }
        rationale = (
            f"Source authority evaluated as {source_authority}.",
            f"Verified fields: {', '.join(verified_fields) if verified_fields else 'none'}.",
            f"Missing fields: {', '.join(missing_fields) if missing_fields else 'none'}.",
            f"Temporal status evaluated as {temporal.value}.",
        )
        return SourceVerificationResult(
            status=status,
            temporal_status=temporal,
            source_authority=source_authority,
            source_urls=source_urls,
            verified_fields=verified_fields,
            missing_fields=missing_fields,
            evidence_hash=sha256_json(evidence_payload),
            rationale=rationale,
        )


@dataclass(frozen=True)
class StrategicIntelligencePlugin:
    plugin_id: str = "cybercore-strategic-intelligence"
    version: str = "1.0.0"
    stage: IntelligenceStage = IntelligenceStage.STRATEGIC_INTELLIGENCE
    order: int = 2

    def execute(
        self,
        context: OpportunityIntelligenceContext,
    ) -> StrategicIntelligenceScore | None:
        verification: SourceVerificationResult = context.output(
            IntelligenceStage.SOURCE_VERIFICATION
        )
        if verification.status is not VerificationStatus.VERIFIED:
            return None

        policy = load_intelligence_policy()
        opportunity = context.opportunity
        metadata = opportunity.metadata
        type_key = _canonical_type(opportunity.opportunity_type)
        baseline = policy["type_baselines"][type_key]
        procurement_type = str(
            metadata.get("procurement_type")
            or metadata.get("notice_type")
            or metadata.get("type")
            or ""
        )
        procurement = policy["procurement_adjustments"].get(procurement_type, {})
        temporal = policy["temporal_adjustments"].get(
            verification.temporal_status.value,
            policy["temporal_adjustments"]["UNKNOWN"],
        )

        searchable = " ".join(
            (
                opportunity.title,
                opportunity.opportunity_type,
                " ".join(opportunity.sectors),
                str(metadata.get("description") or ""),
            )
        ).lower()
        matches = [
            float(entry["score"])
            for entry in policy["sector_alignment"]
            if any(str(keyword).lower() in searchable for keyword in entry["keywords"])
        ]
        sector_fit = max(matches) if matches else float(policy["defaults"]["sector_fit"])

        declared_tier = _strategic_tier(metadata.get("strategic_tier") or metadata.get("strategic_fit"))
        declared_priority = str(metadata.get("priority") or "UNPRIORITIZED")
        tier_score = float(
            policy["strategic_tier_scores"].get(
                declared_tier,
                policy["defaults"]["strategic_signal"],
            )
        )
        priority_score = float(
            policy["priority_signal_scores"].get(
                declared_priority,
                policy["defaults"]["strategic_signal"],
            )
        )
        strategic_alignment = (tier_score + priority_score) / 2

        revenue_probability = _clamp(
            float(baseline["revenue_probability"])
            + float(procurement.get("revenue_probability", 0))
            + float(temporal.get("revenue_probability", 0))
        )
        funding_probability = _clamp(
            float(baseline["funding_probability"])
            + float(procurement.get("funding_probability", 0))
            + float(temporal.get("funding_probability", 0))
        )
        implementation_complexity = float(baseline["implementation_complexity"])
        implementation_complexity += float(procurement.get("implementation_complexity", 0))
        implementation_complexity += float(temporal.get("implementation_complexity", 0))
        implementation_complexity += _complexity_adjustment(context, policy)
        implementation_complexity = _clamp(implementation_complexity)

        dimensions = {
            "sector_fit": _round_one(sector_fit),
            "revenue_probability": _round_one(revenue_probability),
            "funding_probability": _round_one(funding_probability),
            "implementation_complexity": _round_one(implementation_complexity),
            "strategic_alignment": _round_one(strategic_alignment),
        }
        weights = {key: float(value) for key, value in policy["weights"].items()}
        score = _round_one(
            dimensions["sector_fit"] * weights["sector_fit"]
            + dimensions["revenue_probability"] * weights["revenue_probability"]
            + dimensions["funding_probability"] * weights["funding_probability"]
            + (100 - dimensions["implementation_complexity"])
            * weights["implementation_feasibility"]
            + dimensions["strategic_alignment"] * weights["strategic_alignment"]
        )
        thresholds = policy["priority_thresholds"]
        priority = "P0" if score >= thresholds["P0"] else "P1" if score >= thresholds["P1"] else "P2"
        explanation = (
            (
                f"Sector taxonomy matched at {sector_fit:.0f}/100."
                if matches
                else f"No configured sector keyword matched; policy default {sector_fit:.0f}/100 applied."
            ),
            f"Type baseline applied for {type_key}.",
            (
                f"Procurement adjustment applied for {procurement_type}."
                if procurement
                else "No procurement-type adjustment applied."
            ),
            f"Temporal adjustment applied for {verification.temporal_status.value}.",
            f"Declared tier {declared_tier} and priority {declared_priority} informed strategic alignment.",
            "The score is a deterministic policy heuristic, not a statistically calibrated probability.",
        )
        return StrategicIntelligenceScore(
            status="SCORED",
            policy_version=str(policy["version"]),
            methodology="deterministic_weighted_policy",
            dimensions=dimensions,
            weights=weights,
            score=score,
            recommended_priority=priority,
            explanation=explanation,
        )


@dataclass(frozen=True)
class CommercializationRoutingPlugin:
    plugin_id: str = "cybercore-commercialization-routing"
    version: str = "1.0.0"
    stage: IntelligenceStage = IntelligenceStage.COMMERCIALIZATION_ROUTING
    order: int = 3

    def execute(self, context: OpportunityIntelligenceContext) -> CommercializationDecision:
        verification: SourceVerificationResult = context.output(
            IntelligenceStage.SOURCE_VERIFICATION
        )
        score: StrategicIntelligenceScore | None = context.output(
            IntelligenceStage.STRATEGIC_INTELLIGENCE
        )
        policy = load_commercialization_policy()
        opportunity = context.opportunity
        metadata = opportunity.metadata
        type_key = _canonical_type(opportunity.opportunity_type)
        procurement_type = str(
            metadata.get("procurement_type")
            or metadata.get("notice_type")
            or metadata.get("type")
            or ""
        )
        market_entry = str(metadata.get("market_entry") or "")
        candidates: list[str] = list(policy["type_paths"].get(type_key, ()))
        candidates.extend(policy["procurement_type_paths"].get(procurement_type, ()))
        candidates.extend(policy["market_entry_paths"].get(market_entry, ()))
        searchable = " ".join(
            (
                opportunity.title,
                opportunity.opportunity_type,
                " ".join(opportunity.sectors),
                str(metadata.get("program_type") or ""),
                str(metadata.get("revenue_path") or ""),
                str(metadata.get("description") or ""),
            )
        ).lower()
        for rule in policy["program_keyword_paths"]:
            if any(str(keyword).lower() in searchable for keyword in rule["keywords"]):
                candidates.extend(rule["paths"])
        unique = _unique(candidates)
        ordered = tuple(path for path in policy["path_precedence"] if path in unique)
        status = _commercial_status(verification, score, ordered, policy)
        primary_path = ordered[0] if ordered else None
        ready = status is CommercializationStatus.READY_FOR_HUMAN_REVIEW
        rationale = [f"Temporal status evaluated as {verification.temporal_status.value}."]
        if ordered:
            rationale.append(f"Candidate paths identified: {', '.join(ordered)}.")
        rationale.append(_commercial_rationale(status))
        return CommercializationDecision(
            status=status,
            policy_version=str(policy["version"]),
            candidate_paths=ordered,
            primary_path=primary_path,
            rationale=tuple(rationale),
            treasury_labs_status=(
                str(policy["treasury_labs"]["ready_status"])
                if ready
                else str(policy["treasury_labs"]["blocked_status"])
            ),
            automatic_dispatch=False,
            handoff_executed=False,
        )


@dataclass(frozen=True)
class MaturityOutputPlugin:
    plugin_id: str = "cybercore-maturity-output"
    version: str = "1.0.0"
    stage: IntelligenceStage = IntelligenceStage.MATURITY_OUTPUT
    order: int = 4

    def execute(self, context: OpportunityIntelligenceContext) -> MaturityDecision:
        commercialization: CommercializationDecision = context.output(
            IntelligenceStage.COMMERCIALIZATION_ROUTING
        )
        mapping = {
            CommercializationStatus.READY_FOR_HUMAN_REVIEW: MaturityDecision(
                stage=MaturityStage.HUMAN_REVIEW,
                order=50,
                disposition="REQUIRES_HUMAN_DECISION",
                human_decision_required=True,
                actionable=True,
                reason="Verified, scored, routed, and temporally actionable; explicit human review is required.",
            ),
            CommercializationStatus.CLOSED_NO_ACTION: MaturityDecision(
                stage=MaturityStage.CLOSED,
                order=90,
                disposition="NO_ACTION_HISTORICAL",
                human_decision_required=False,
                actionable=False,
                reason="The opportunity deadline passed or the authoritative status is terminal.",
            ),
            CommercializationStatus.MONITOR_FORECAST: MaturityDecision(
                stage=MaturityStage.FORECAST_MONITOR,
                order=45,
                disposition="MONITOR_FORECAST",
                human_decision_required=False,
                actionable=False,
                reason="The opportunity is a forecast and is not open for action.",
            ),
            CommercializationStatus.PROGRAM_DISCOVERY_ONLY: MaturityDecision(
                stage=MaturityStage.PROGRAM_DISCOVERY,
                order=45,
                disposition="DISCOVER_SPECIFIC_CHILD_OPPORTUNITY",
                human_decision_required=False,
                actionable=False,
                reason="The evidence describes a program category rather than one actionable opportunity.",
            ),
            CommercializationStatus.SOURCE_VERIFICATION_REQUIRED: MaturityDecision(
                stage=MaturityStage.SOURCE_DISCOVERY,
                order=20,
                disposition="REQUIRES_AUTHORITATIVE_SOURCE_EVIDENCE",
                human_decision_required=False,
                actionable=False,
                reason="Issuer, identifier, deadline, or authoritative source evidence is incomplete.",
            ),
            CommercializationStatus.NO_ROUTE_IDENTIFIED: MaturityDecision(
                stage=MaturityStage.STRATEGIC_INTELLIGENCE,
                order=40,
                disposition="REQUIRES_ROUTE_REVIEW",
                human_decision_required=False,
                actionable=False,
                reason="The record is verified and scored, but no defensible commercial path was identified.",
            ),
        }
        return mapping[commercialization.status]


def _canonical_type(value: str) -> str:
    text = value.strip().lower()
    if any(token in text for token in ("grant", "funding", "cooperative agreement")):
        return "funding"
    if any(token in text for token in ("challenge", "prize", "accelerator")):
        return "challenge_prize"
    if any(token in text for token in ("technology need", "commercialization", "technology transfer")):
        return "technology_need"
    return "procurement"


def _strategic_tier(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"tier 1", "high", "very high", "critical"}:
        return "Tier 1"
    if text in {"tier 2", "medium-high", "moderate-high", "medium", "moderate"}:
        return "Tier 2"
    if text in {"tier 3", "medium-low", "low-medium", "low", "very low"}:
        return "Tier 3"
    return "Unassessed"


def _complexity_adjustment(
    context: OpportunityIntelligenceContext,
    policy: Mapping[str, Any],
) -> float:
    rules = policy["complexity_rules"]
    metadata = context.opportunity.metadata
    adjustment = min(len(context.opportunity.eligibility), 5) * float(
        rules["per_eligibility_item"]
    )
    adjustment += min(len(_strings(metadata.get("compliance_requirements"))), 5) * float(
        rules["per_compliance_item"]
    )
    adjustment += min(len(_strings(metadata.get("registration_requirements"))), 5) * float(
        rules["per_registration_item"]
    )
    if context.opportunity.jurisdiction.strip().lower() not in {
        "united states",
        "u.s.",
        "usa",
    }:
        adjustment += float(rules["international_jurisdiction"])
    revenue_path = str(metadata.get("revenue_path") or "")
    if "partnership" in revenue_path.lower() or "consortium" in revenue_path.lower():
        adjustment += float(rules["consortium_or_partnership"])
    return min(adjustment, float(rules["maximum_adjustment"]))


def _commercial_status(
    verification: SourceVerificationResult,
    score: StrategicIntelligenceScore | None,
    paths: Sequence[str],
    policy: Mapping[str, Any],
) -> CommercializationStatus:
    temporal = verification.temporal_status
    if temporal is TemporalStatus.PROGRAM_ONLY:
        return CommercializationStatus.PROGRAM_DISCOVERY_ONLY
    if temporal is TemporalStatus.FORECAST:
        return CommercializationStatus.MONITOR_FORECAST
    if temporal is TemporalStatus.CLOSED:
        return CommercializationStatus.CLOSED_NO_ACTION
    if verification.status is not VerificationStatus.VERIFIED or temporal is TemporalStatus.UNKNOWN:
        return CommercializationStatus.SOURCE_VERIFICATION_REQUIRED
    if score is None:
        return CommercializationStatus.SOURCE_VERIFICATION_REQUIRED
    if not paths:
        return CommercializationStatus.NO_ROUTE_IDENTIFIED
    if temporal.value in policy["ready_temporal_statuses"]:
        return CommercializationStatus.READY_FOR_HUMAN_REVIEW
    return CommercializationStatus.NO_ROUTE_IDENTIFIED


def _commercial_rationale(status: CommercializationStatus) -> str:
    return {
        CommercializationStatus.READY_FOR_HUMAN_REVIEW: (
            "The record is verified, scored, routed, and must receive explicit human review."
        ),
        CommercializationStatus.CLOSED_NO_ACTION: (
            "The observed deadline passed; new submission or bid activity is blocked."
        ),
        CommercializationStatus.MONITOR_FORECAST: (
            "The source is a forecast; monitor for a released solicitation before action."
        ),
        CommercializationStatus.PROGRAM_DISCOVERY_ONLY: (
            "The source verifies a program category, not one specific actionable opportunity."
        ),
        CommercializationStatus.SOURCE_VERIFICATION_REQUIRED: (
            "Strict source verification or temporal actionability is incomplete."
        ),
        CommercializationStatus.NO_ROUTE_IDENTIFIED: (
            "No defensible commercialization path met the routing policy."
        ),
    }[status]
