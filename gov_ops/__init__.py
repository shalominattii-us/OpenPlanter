"""Government opportunity ingestion spine."""

from .opportunity import Opportunity
from .sam_gov import SAMGovOpportunitiesClient, normalize_sam_opportunity

__all__ = ["Opportunity", "SAMGovOpportunitiesClient", "normalize_sam_opportunity"]
