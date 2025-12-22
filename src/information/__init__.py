"""
Information Collection Module - Layer 1 of 4-layer architecture.

This module handles:
- Time-sensitive information structuring
- News categorization by lead time
- Data validation and freshness tracking
"""
from .collector import InformationCollector
from .models import (
    TimedInformation,
    NewsItem,
    MarketContext,
    TimeCategory,
)

__all__ = [
    "InformationCollector",
    "TimedInformation",
    "NewsItem",
    "MarketContext",
    "TimeCategory",
]
