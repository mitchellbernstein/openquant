"""Data resolver - chains multiple data providers with fallback logic.

The resolver tries each provider in priority order and returns the
first successful result. If a provider raises or returns empty data,
it falls back to the next one in the chain.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import List, Optional

from openquant.data.protocol import (
    DataProvider,
    Price,
    InsiderTrade,
    FinancialStatement,
    AnalystEstimate,
    NewsItem,
    CompanyInfo,
)
from openquant.data.yfinance_provider import YFinanceProvider
from openquant.data.quantfetch_provider import QuantFetchProvider
from openquant.data.sec_edgar_provider import SECEdgarProvider

logger = logging.getLogger(__name__)


class DataResolver:
    """Chains data providers with automatic fallback.

    Tries each provider in order. If a provider returns an empty result
    or raises an exception, the resolver moves on to the next provider.

    Usage:
        resolver = DataResolver([QuantFetchProvider(), YFinanceProvider()])
        prices = resolver.get_prices("AAPL", start, end)
    """

    def __init__(self, providers: Optional[List[DataProvider]] = None):
        self._providers: List[DataProvider] = providers or []

    @property
    def providers(self) -> List[DataProvider]:
        """Current list of providers in priority order."""
        return list(self._providers)

    def add_provider(self, provider: DataProvider) -> None:
        """Append a provider to the end of the chain."""
        self._providers.append(provider)

    def add_provider_first(self, provider: DataProvider) -> None:
        """Insert a provider at the front of the chain (highest priority)."""
        self._providers.insert(0, provider)

    # ------------------------------------------------------------------
    # Core resolution logic
    # ------------------------------------------------------------------

    def _resolve(self, method_name: str, *args, accept_empty: bool = False, **kwargs):
        """Try each provider's *method_name* until one succeeds.

        If *accept_empty* is False (default), empty lists/None count as
        failure and trigger fallback. If True, empty results are accepted.
        Returns the first non-empty result, or the last result if all fail.
        """
        last_result = None
        for provider in self._providers:
            try:
                method = getattr(provider, method_name, None)
                if method is None:
                    continue
                result = method(*args, **kwargs)
                # Check if result is usable
                if result is None:
                    logger.debug("Resolver: %s.%s returned None, trying next", provider.name, method_name)
                    continue
                if isinstance(result, list) and not result and not accept_empty:
                    logger.debug("Resolver: %s.%s returned empty list, trying next", provider.name, method_name)
                    continue
                if result:
                    logger.debug("Resolver: %s.%s succeeded", provider.name, method_name)
                    return result
                last_result = result
            except Exception as exc:
                logger.warning("Resolver: %s.%s failed: %s", provider.name, method_name, exc)
                continue

        # Return whatever we got (could be empty list or None)
        return last_result if last_result is not None else ([] if method_name != "get_company_info" else None)

    # ------------------------------------------------------------------
    # DataProvider-style public API
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "DataResolver"

    @property
    def is_free(self) -> bool:
        """True if any provider in the chain is free."""
        return any(p.is_free for p in self._providers)

    def get_prices(self, ticker: str, start: date, end: date) -> List[Price]:
        return self._resolve("get_prices", ticker, start, end)

    def get_insider_trades(self, ticker: str, days: int = 90) -> List[InsiderTrade]:
        return self._resolve("get_insider_trades", ticker, days)

    def get_financials(self, ticker: str, statement_type: str = "income") -> List[FinancialStatement]:
        return self._resolve("get_financials", ticker, statement_type)

    def get_analyst_estimates(self, ticker: str) -> List[AnalystEstimate]:
        return self._resolve("get_analyst_estimates", ticker)

    def get_news(self, ticker: str, limit: int = 10) -> List[NewsItem]:
        return self._resolve("get_news", ticker, limit)

    def get_company_info(self, ticker: str) -> Optional[CompanyInfo]:
        return self._resolve("get_company_info", ticker)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "DataResolver":
        """Build a resolver chain from environment variables.

        Auto-detects which providers are available:
          - QUANTFETCH_API_KEY set  -> include QuantFetchProvider
          - Always include YFinanceProvider (free)
          - Always include SECEdgarProvider (free)

        The order is: QuantFetch (if key present) > yfinance > SEC EDGAR
        """
        providers: List[DataProvider] = []

        quantfetch_key = os.environ.get("QUANTFETCH_API_KEY", "")
        if quantfetch_key:
            try:
                providers.append(QuantFetchProvider(api_key=quantfetch_key))
                logger.info("DataResolver: QuantFetch provider enabled (API key found)")
            except Exception as exc:
                logger.warning("DataResolver: failed to init QuantFetch: %s", exc)

        # yfinance is always available
        providers.append(YFinanceProvider())

        # SEC EDGAR is always available (free, just slow)
        providers.append(SECEdgarProvider())

        logger.info("DataResolver: chain = [%s]", ", ".join(p.name for p in providers))
        return cls(providers)

    @classmethod
    def default(cls) -> "DataResolver":
        """Create the default resolver chain: QuantFetch > yfinance > SEC EDGAR.

        QuantFetch is included only if QUANTFETCH_API_KEY is set.
        Equivalent to from_env().
        """
        return cls.from_env()
