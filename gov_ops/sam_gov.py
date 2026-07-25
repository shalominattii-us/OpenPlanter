from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from hashlib import sha256
from typing import Any

from .opportunity import Opportunity


class SAMGovOpportunitiesClient:
    """Minimal client for the SAM.gov Get Opportunities Public API v2."""

    endpoint = "https://api.sam.gov/opportunities/v2/search"

    def __init__(self, api_key: str, timeout: int = 30):
        if not api_key:
            raise ValueError("SAM.gov API key is required")
        self.api_key = api_key
        self.timeout = timeout

    def search(
        self,
        *,
        posted_from: str,
        posted_to: str,
        limit: int = 10,
        offset: int = 0,
        title: str | None = None,
        notice_type: str | None = None,
        naics: str | None = None,
        organization: str | None = None,
    ) -> dict[str, Any]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if offset < 0:
            raise ValueError("offset cannot be negative")

        params: dict[str, Any] = {
            "api_key": self.api_key,
            "postedFrom": posted_from,
            "postedTo": posted_to,
            "limit": limit,
            "offset": offset,
        }
        optional = {
            "title": title,
            "ptype": notice_type,
            "ncode": naics,
            "organizationName": organization,
        }
        params.update({key: value for key, value in optional.items() if value})

        url = f"{self.endpoint}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "OpenPlanter-GovOps/0.1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"SAM.gov returned HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"SAM.gov request failed: {exc.reason}") from exc


def _first_contact(record: dict[str, Any]) -> dict[str, Any]:
    contacts = record.get("pointOfContact") or []
    if not contacts:
        return {}
    contact = contacts[0] or {}
    return {
        "name": contact.get("fullname") or contact.get("fullName"),
        "email": contact.get("email"),
        "phone": contact.get("phone"),
        "type": contact.get("type"),
    }


def _attachments(record: dict[str, Any]) -> list[dict[str, Any]]:
    links = record.get("resourceLinks") or []
    return [{"url": link} for link in links if link]


def normalize_sam_opportunity(record: dict[str, Any]) -> Opportunity:
    """Convert one SAM.gov opportunity record into the canonical contract."""

    source_record_id = str(record.get("noticeId") or "").strip()
    title = str(record.get("title") or "").strip()
    if not source_record_id or not title:
        raise ValueError("SAM.gov record requires noticeId and title")

    stable_id = sha256(f"sam.gov:{source_record_id}".encode("utf-8")).hexdigest()[:24]
    place = record.get("placeOfPerformance") or {}
    office_address = record.get("officeAddress") or {}
    naics = record.get("naicsCode")
    ui_link = record.get("uiLink")

    opportunity = Opportunity(
        opportunity_id=f"opp_{stable_id}",
        source="sam.gov",
        source_record_id=source_record_id,
        title=title,
        agency=record.get("fullParentPathName") or record.get("department"),
        office=record.get("office"),
        solicitation_number=record.get("solicitationNumber"),
        notice_type=record.get("type"),
        posted_date=record.get("postedDate"),
        due_date=record.get("responseDeadLine"),
        naics=[str(naics)] if naics else [],
        psc=record.get("classificationCode"),
        set_aside=record.get("typeOfSetAsideDescription") or record.get("typeOfSetAside"),
        location={
            "city": place.get("city", {}).get("name") if isinstance(place.get("city"), dict) else place.get("city"),
            "state": place.get("state", {}).get("code") if isinstance(place.get("state"), dict) else place.get("state"),
            "country": place.get("country", {}).get("code") if isinstance(place.get("country"), dict) else place.get("country"),
            "zip": place.get("zip"),
        },
        description=record.get("description"),
        attachments=_attachments(record),
        contact=_first_contact(record),
        urls=[ui_link] if ui_link else [],
        metadata={
            "archive_type": record.get("archiveType"),
            "archive_date": record.get("archiveDate"),
            "base_type": record.get("baseType"),
            "active": record.get("active"),
            "office_address": office_address,
            "raw_source": record,
        },
    )
    opportunity.validate()
    return opportunity


def normalize_search_response(payload: dict[str, Any]) -> list[Opportunity]:
    records = payload.get("opportunitiesData") or []
    if not isinstance(records, list):
        raise ValueError("SAM.gov response opportunitiesData must be a list")
    return [normalize_sam_opportunity(record) for record in records]
