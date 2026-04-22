"""Data provider protocol - pluggable interface for market data sources.

Every data source (QuantFetch, yfinance, SEC EDGAR) implements this protocol.
Users can add their own providers by implementing the same interface.
"""

from __future__ import annotations
from typing import Protocol, Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class Price:
    """Single price data point."""
    ticker: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    source: str = ""


@dataclass
class InsiderTrade:
    """Insider trading event."""
    ticker: str
    insider_name: str
    title: str
    transaction_type: str  # "BUY" or "SELL"
    shares: int
    price: float
    value: float
    date: date
    source: str = ""


@dataclass
class FinancialStatement:
    """Financial statement data."""
    ticker: str
    statement_type: str  # "income", "balance", "cashflow"
    period: str
    period_end_date: date
    items: Dict[str, Any]
    source: str = ""


@dataclass
class AnalystEstimate:
    """Analyst consensus estimate."""
    ticker: str
    estimate_type: str  # "eps", "revenue", "price_target"
    period: str
    consensus_avg: float
    consensus_low: float
    consensus_high: float
    number_of_analysts: int
    source: str = ""


@dataclass
class NewsItem:
    """News article."""
    title: str
    source: str
    url: str
    date: datetime
    ticker: str = ""
    summary: str = ""


@dataclass
class CompanyInfo:
    """Company metadata."""
    ticker: str
    name: str
    cik: str = ""
    sector: str = ""
    industry: str = ""
    market_cap: float = 0.0


class DataProvider(Protocol):
    """Protocol for market data providers.
    
    Implement this to add a new data source to OpenQuant.
    All methods are optional - return empty lists if data is unavailable.
    """

    @property
    def name(self) -> str:
        """Human-readable name of this provider."""
        ...

    @property
    def is_free(self) -> bool:
        """Whether this provider requires an API key."""
        ...

    def get_prices(
        self, ticker: str, start: date, end: date
    ) -> List[Price]:
        """Get historical price data."""
        ...

    def get_insider_trades(
        self, ticker: str, days: int = 90
    ) -> List[InsiderTrade]:
        """Get recent insider trades."""
        ...

    def get_financials(
        self, ticker: str, statement_type: str = "income"
    ) -> List[FinancialStatement]:
        """Get financial statements."""
        ...

    def get_analyst_estimates(
        self, ticker: str
    ) -> List[AnalystEstimate]:
        """Get analyst consensus estimates."""
        ...

    def get_news(
        self, ticker: str, limit: int = 10
    ) -> List[NewsItem]:
        """Get recent news for a ticker."""
        ...

    def get_company_info(
        self, ticker: str
    ) -> Optional[CompanyInfo]:
        """Get company metadata."""
        ...
