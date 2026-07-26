"""Source-specific adapters for the Universal Opportunity Engine."""

from .sam_gov import SAMGovClient, SAMGovSource, normalize_sam_record

__all__ = ["SAMGovClient", "SAMGovSource", "normalize_sam_record"]
