from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable


RawRecord = Mapping[str, Any]
NormalizedRecord = Mapping[str, Any]


@dataclass(frozen=True)
class SourceMetadata:
    """Versioned identity for one opportunity source adapter."""

    source_name: str
    source_url: str
    adapter_version: str

    def __post_init__(self) -> None:
        if not self.source_name.strip():
            raise ValueError("source_name is required")
        if not self.source_url.strip():
            raise ValueError("source_url is required")
        if not self.adapter_version.strip():
            raise ValueError("adapter_version is required")


@runtime_checkable
class OpportunitySource(Protocol):
    """Contract implemented by every external opportunity source.

    Fetching and source-specific normalization remain outside the canonical domain.
    The daily intake consumes only validated normalized mappings.
    """

    def metadata(self) -> SourceMetadata:
        ...

    def fetch(self) -> Iterable[RawRecord]:
        ...

    def normalize(self, record: RawRecord) -> NormalizedRecord:
        ...

    def validate(self, record: NormalizedRecord) -> None:
        ...


def collect_normalized(source: OpportunitySource) -> tuple[NormalizedRecord, ...]:
    """Fetch, normalize, and validate each source record exactly once."""

    normalized: list[NormalizedRecord] = []
    for raw_record in source.fetch():
        record = source.normalize(raw_record)
        source.validate(record)
        normalized.append(record)
    return tuple(normalized)
