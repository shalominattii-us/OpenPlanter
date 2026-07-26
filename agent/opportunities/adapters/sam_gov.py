from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping
import json
import urllib.error
import urllib.parse
import urllib.request

from ..sources import NormalizedRecord, RawRecord, SourceMetadata


SAM_GOV_ENDPOINT = "https://api.sam.gov/opportunities/v2/search"
SAM_GOV_ADAPTER_VERSION = "1.0.0"


@dataclass(frozen=True)
class SAMGovClient:
    """Minimal SAM.gov Opportunities API v2 client.

    The client returns raw source mappings only. Canonical domain construction is
    deliberately handled later by ``UniversalIntakeAdapter``.
    """

    api_key: str
    timeout_seconds: int = 30
    endpoint: str = SAM_GOV_ENDPOINT

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("SAM.gov API key is required")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

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
    ) -> tuple[RawRecord, ...]:
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
                "User-Agent": "OpenPlanter-UniversalOpportunity/1.0",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"SAM.gov returned HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"SAM.gov request failed: {exc.reason}") from exc

        records = payload.get("opportunitiesData") or []
        if not isinstance(records, list):
            raise ValueError("SAM.gov response opportunitiesData must be a list")
        return tuple(record for record in records if isinstance(record, Mapping))


def normalize_sam_record(record: RawRecord) -> dict[str, Any]:
    """Normalize one SAM.gov record into the universal intake mapping contract."""

    notice_id = _text(record.get("noticeId"))
    title = _text(record.get("title"))
    if not notice_id or not title:
        raise ValueError("SAM.gov record requires noticeId and title")

    place = _mapping(record.get("placeOfPerformance"))
    contact = _first_contact(record.get("pointOfContact"))
    resource_links = record.get("resourceLinks") or ()
    if isinstance(resource_links, str):
        resource_links = (resource_links,)

    ui_link = _text(record.get("uiLink"))
    source_url = ui_link or f"https://sam.gov/opp/{notice_id}/view"
    raw_deadline = _text(record.get("responseDeadLine"))

    normalized: dict[str, Any] = {
        "external_id": notice_id,
        "record_id": notice_id,
        "title": title,
        "source": "SAM.gov",
        "source_url": source_url,
        "issuer": _text(record.get("fullParentPathName") or record.get("department")),
        "agency": _text(record.get("fullParentPathName") or record.get("department")),
        "jurisdiction": "United States",
        "type": _text(record.get("type")) or "Federal opportunity",
        "status": "open" if record.get("active", True) else "inactive",
        "published_date": _date_prefix(record.get("postedDate")),
        "deadline": _date_prefix(raw_deadline),
        "attachments": tuple(str(link) for link in resource_links if link),
        "submission_path": source_url,
        "sectors": _as_tuple(record.get("naicsCode")),
        "description": _text(record.get("description")),
        "solicitation_number": _text(record.get("solicitationNumber")),
        "office": _text(record.get("office")),
        "naics": _as_tuple(record.get("naicsCode")),
        "psc": _text(record.get("classificationCode")),
        "set_aside": _text(
            record.get("typeOfSetAsideDescription") or record.get("typeOfSetAside")
        ),
        "contact": contact,
        "location": {
            "city": _nested_text(place.get("city"), "name"),
            "state": _nested_text(place.get("state"), "code"),
            "country": _nested_text(place.get("country"), "code"),
            "postal_code": _text(place.get("zip")),
        },
        "sam_raw": dict(record),
    }
    return normalized


@dataclass(frozen=True)
class SAMGovSource:
    """Concrete ``OpportunitySource`` for one bounded SAM.gov query."""

    client: SAMGovClient
    posted_from: str
    posted_to: str
    limit: int = 10
    offset: int = 0
    title: str | None = None
    notice_type: str | None = None
    naics: str | None = None
    organization: str | None = None

    def metadata(self) -> SourceMetadata:
        return SourceMetadata(
            source_name="SAM.gov",
            source_url="https://sam.gov/",
            adapter_version=SAM_GOV_ADAPTER_VERSION,
        )

    def fetch(self) -> Iterable[RawRecord]:
        return self.client.search(
            posted_from=self.posted_from,
            posted_to=self.posted_to,
            limit=self.limit,
            offset=self.offset,
            title=self.title,
            notice_type=self.notice_type,
            naics=self.naics,
            organization=self.organization,
        )

    def normalize(self, record: RawRecord) -> NormalizedRecord:
        return normalize_sam_record(record)

    def validate(self, record: NormalizedRecord) -> None:
        required = ("external_id", "title", "source", "source_url", "jurisdiction")
        missing = [name for name in required if not _text(record.get(name))]
        if missing:
            raise ValueError(
                "SAM.gov normalized record is missing required fields: "
                + ", ".join(missing)
            )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _date_prefix(value: Any) -> str | None:
    text = _text(value)
    return text[:10] if text else None


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        return (value,)
    try:
        return tuple(str(item) for item in value if item not in (None, ""))
    except TypeError:
        return (str(value),)


def _nested_text(value: Any, key: str) -> str | None:
    if isinstance(value, Mapping):
        return _text(value.get(key))
    return _text(value)


def _first_contact(value: Any) -> dict[str, Any]:
    if not isinstance(value, list) or not value:
        return {}
    first = _mapping(value[0])
    return {
        "name": _text(first.get("fullname") or first.get("fullName")),
        "email": _text(first.get("email")),
        "phone": _text(first.get("phone")),
        "type": _text(first.get("type")),
    }
