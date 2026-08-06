from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CybercoreBatch:
    batch_id: str
    batch_date: str
    authorization: str
    records: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        if not self.batch_id.strip() or not self.batch_date.strip():
            raise ValueError("Cybercore batch id and date are required")
        if self.authorization != "human_required":
            raise ValueError("Cybercore batch authorization must be human_required")


def load_cybercore_batch(
    batch_path: Path,
    *,
    evidence_path: Path | None = None,
) -> CybercoreBatch:
    batch = _object(batch_path)
    opportunities = batch.get("opportunities")
    if not isinstance(opportunities, list) or not opportunities:
        raise ValueError("Cybercore batch opportunities must be a non-empty array")
    evidence_by_title = _evidence_by_title(evidence_path) if evidence_path else {}
    records = tuple(
        _normalize_record(
            item,
            batch_id=str(batch.get("batch_id") or ""),
            batch_date=str(batch.get("batch_date") or ""),
            batch_source=str(batch.get("source") or "cybercore-batch"),
            evidence=evidence_by_title.get(str(item.get("title") or "")),
        )
        for item in opportunities
        if isinstance(item, Mapping)
    )
    if len(records) != len(opportunities):
        raise ValueError("every Cybercore opportunity must be a JSON object")
    return CybercoreBatch(
        batch_id=str(batch.get("batch_id") or ""),
        batch_date=str(batch.get("batch_date") or ""),
        authorization=str(batch.get("authorization") or ""),
        records=records,
    )


def _normalize_record(
    record: Mapping[str, Any],
    *,
    batch_id: str,
    batch_date: str,
    batch_source: str,
    evidence: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    title = str(record.get("title") or "").strip()
    if not title:
        raise ValueError("Cybercore opportunity title is required")
    evidence = evidence or {}
    source_urls = tuple(str(item) for item in evidence.get("source_urls", ()) if item)
    source_url = source_urls[0] if source_urls else f"cybercore://{batch_id}/{_slug(title)}"
    classification = str(evidence.get("classification") or "UNVERIFIED")
    official_status = evidence.get("official_status")
    funding_amount = evidence.get("value_amount")
    if funding_amount is None:
        funding_amount = record.get("funding_amount")
    identifier = evidence.get("identifier") or record.get("identifier")
    issuer = evidence.get("issuer") or record.get("issuer")
    return {
        "external_id": identifier,
        "record_id": identifier,
        "title": evidence.get("official_title") or title,
        "intake_title": title,
        "source": evidence.get("source_authority") or batch_source,
        "source_authority": evidence.get("source_authority") or batch_source,
        "source_url": source_url,
        "source_urls": source_urls,
        "issuer": issuer,
        "agency": issuer,
        "jurisdiction": record.get("jurisdiction") or "Unknown",
        "type": record.get("opportunity_type") or "Unknown",
        "opportunity_type": record.get("opportunity_type") or "Unknown",
        "program_type": record.get("program_type"),
        "procurement_type": record.get("procurement_type"),
        "market_entry": record.get("market_entry"),
        "status": _record_status(classification, official_status),
        "classification": classification,
        "published_date": evidence.get("publication_date") or record.get("publication_date"),
        "deadline": evidence.get("deadline") or record.get("deadline"),
        "eligibility": evidence.get("eligibility") or record.get("eligibility") or (),
        "amount_max": funding_amount,
        "currency": evidence.get("value_currency") or "USD",
        "submission_path": evidence.get("submission_method") or record.get("submission_method"),
        "sectors": (record.get("sector"),) if record.get("sector") else (),
        "sector": record.get("sector"),
        "strategic_fit": record.get("strategic_fit"),
        "strategic_tier": record.get("strategic_fit"),
        "priority": record.get("priority") or "UNPRIORITIZED",
        "revenue_path": record.get("revenue_path"),
        "registration_requirements": record.get("registration_requirements") or (),
        "compliance_requirements": record.get("compliance_requirements") or (),
        "official_status": official_status,
        "issuer_verified": bool(evidence.get("issuer_verified")),
        "identifier_verified": bool(evidence.get("identifier_verified")),
        "deadline_verified": bool(evidence.get("deadline_verified")),
        "evidence_summary": evidence.get("evidence_summary"),
        "evidence_confidence": evidence.get("confidence"),
        "source_checked_at": evidence.get("retrieved_at") or record.get("source_checked_at"),
        "batch_id": batch_id,
        "batch_date": batch_date,
        "authorization": "human_required",
    }


def _evidence_by_title(path: Path) -> Mapping[str, Mapping[str, Any]]:
    payload = _object(path)
    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        raise TypeError("Cybercore evidence must be an array")
    indexed: dict[str, Mapping[str, Any]] = {}
    for item in evidence:
        if not isinstance(item, Mapping):
            raise TypeError("every Cybercore evidence item must be a JSON object")
        title = str(item.get("record_title") or "").strip()
        if not title:
            raise ValueError("Cybercore evidence record_title is required")
        if title in indexed:
            raise ValueError(f"duplicate Cybercore evidence title: {title}")
        indexed[title] = item
    return indexed


def _object(path: Path) -> Mapping[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"JSON input must be an object: {path}")
    return payload


def _record_status(classification: str, official_status: Any) -> str:
    if classification == "VERIFIED_FORECAST":
        return "forecast"
    if classification == "VERIFIED_PROGRAM":
        return "program"
    if classification == "HISTORICAL":
        return "closed"
    if classification == "VERIFIED_ACTIVE":
        return str(official_status or "open")
    return "unknown"


def _slug(value: str) -> str:
    return "-".join(part for part in value.lower().replace("/", " ").split() if part)
