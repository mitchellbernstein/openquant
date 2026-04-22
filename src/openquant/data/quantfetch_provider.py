"""QuantFetch data provider - premium market data via the QuantFetch API."""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import List, Optional, Dict, Any

import httpx

from openquant.data.protocol import (
    Price,
    InsiderTrade,
    FinancialStatement,
    AnalystEstimate,
    NewsItem,
    CompanyInfo,
)

logger = logging.getLogger(__name__)

QUANTFETCH_BASE_URL = "https://api.quantfetch.ai"
_DEFAULT_TIMEOUT = 15.0


class QuantFetchProvider:
    """Data provider backed by the QuantFetch API.

    Requires QUANTFETCH_API_KEY environment variable.
    Falls back to YFinanceProvider on API errors.
    """

    def __init__(self, api_key: Optional[str] = None, timeout: float = _DEFAULT_TIMEOUT):
        self._api_key = api_key or os.environ.get("QUANTFETCH_API_KEY", "")
        self._timeout = timeout
        self._client = httpx.Client(
            base_url=QUANTFETCH_BASE_URL,
            headers={"X-API-Key": self._api_key},
            timeout=timeout,
        )

    @property
    def name(self) -> str:
        return "QuantFetch"

    @property
    def is_free(self) -> bool:
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """Make a GET request to QuantFetch API, return JSON or None on error."""
        try:
            resp = self._client.get(path, params=params or {})
            if resp.status_code == 429:
                logger.warning("QuantFetch: rate limited on %s", path)
                return None
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("QuantFetch HTTP %s on %s: %s", exc.response.status_code, path, exc)
            return None
        except httpx.RequestError as exc:
            logger.error("QuantFetch request error on %s: %s", path, exc)
            return None
        except Exception as exc:
            logger.error("QuantFetch unexpected error on %s: %s", path, exc)
            return None

    def _fallback(self):
        """Lazy-load YFinanceProvider for fallback."""
        from openquant.data.yfinance_provider import YFinanceProvider
        return YFinanceProvider()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_prices(self, ticker: str, start: date, end: date) -> List[Price]:
        data = self._get("/prices", {"ticker": ticker, "start": start.isoformat(), "end": end.isoformat()})
        if data is None or "data" not in data:
            logger.info("QuantFetch: falling back to yfinance for prices of %s", ticker)
            return self._fallback().get_prices(ticker, start, end)

        prices: List[Price] = []
        for item in data["data"]:
            try:
                prices.append(
                    Price(
                        ticker=ticker,
                        date=date.fromisoformat(item["date"]),
                        open=float(item.get("open", 0)),
                        high=float(item.get("high", 0)),
                        low=float(item.get("low", 0)),
                        close=float(item.get("close", 0)),
                        volume=int(item.get("volume", 0)),
                        source=self.name,
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:
                logger.debug("QuantFetch: skipping price row: %s", exc)
        return prices

    def get_insider_trades(self, ticker: str, days: int = 90) -> List[InsiderTrade]:
        data = self._get("/insider-trades", {"ticker": ticker, "days": days})
        if data is None or "data" not in data:
            logger.info("QuantFetch: falling back to yfinance for insider trades of %s", ticker)
            return self._fallback().get_insider_trades(ticker, days)

        trades: List[InsiderTrade] = []
        for item in data["data"]:
            try:
                trades.append(
                    InsiderTrade(
                        ticker=ticker,
                        insider_name=str(item.get("insider_name", "")),
                        title=str(item.get("title", "")),
                        transaction_type=str(item.get("transaction_type", "")).upper(),
                        shares=int(item.get("shares", 0)),
                        price=float(item.get("price", 0)),
                        value=float(item.get("value", 0)),
                        date=date.fromisoformat(item["date"]),
                        source=self.name,
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:
                logger.debug("QuantFetch: skipping insider trade row: %s", exc)
        return trades

    def get_financials(self, ticker: str, statement_type: str = "income") -> List[FinancialStatement]:
        data = self._get("/financials", {"ticker": ticker, "type": statement_type})
        if data is None or "data" not in data:
            logger.info("QuantFetch: falling back to yfinance for financials of %s", ticker)
            return self._fallback().get_financials(ticker, statement_type)

        statements: List[FinancialStatement] = []
        for item in data["data"]:
            try:
                statements.append(
                    FinancialStatement(
                        ticker=ticker,
                        statement_type=statement_type,
                        period=str(item.get("period", "annual")),
                        period_end_date=date.fromisoformat(item["period_end_date"]),
                        items=item.get("items", {}),
                        source=self.name,
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:
                logger.debug("QuantFetch: skipping financial row: %s", exc)
        return statements

    def get_analyst_estimates(self, ticker: str) -> List[AnalystEstimate]:
        data = self._get("/analyst-estimates", {"ticker": ticker})
        if data is None or "data" not in data:
            logger.info("QuantFetch: falling back to yfinance for analyst estimates of %s", ticker)
            return self._fallback().get_analyst_estimates(ticker)

        estimates: List[AnalystEstimate] = []
        for item in data["data"]:
            try:
                estimates.append(
                    AnalystEstimate(
                        ticker=ticker,
                        estimate_type=str(item.get("estimate_type", "")),
                        period=str(item.get("period", "")),
                        consensus_avg=float(item.get("consensus_avg", 0)),
                        consensus_low=float(item.get("consensus_low", 0)),
                        consensus_high=float(item.get("consensus_high", 0)),
                        number_of_analysts=int(item.get("number_of_analysts", 0)),
                        source=self.name,
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:
                logger.debug("QuantFetch: skipping analyst estimate row: %s", exc)
        return estimates

    def get_news(self, ticker: str, limit: int = 10) -> List[NewsItem]:
        data = self._get("/news", {"ticker": ticker, "limit": limit})
        if data is None or "data" not in data:
            logger.info("QuantFetch: falling back to yfinance for news of %s", ticker)
            return self._fallback().get_news(ticker, limit)

        items: List[NewsItem] = []
        for item in data["data"]:
            try:
                dt = item.get("date", "")
                parsed_date = datetime.fromisoformat(dt) if isinstance(dt, str) else datetime.now()
                items.append(
                    NewsItem(
                        title=str(item.get("title", "")),
                        source=str(item.get("source", "")),
                        url=str(item.get("url", "")),
                        date=parsed_date,
                        ticker=ticker,
                        summary=str(item.get("summary", "")),
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:
                logger.debug("QuantFetch: skipping news row: %s", exc)
        return items

    def get_company_info(self, ticker: str) -> Optional[CompanyInfo]:
        data = self._get("/company/facts", {"ticker": ticker})
        if data is None or "data" not in data:
            logger.info("QuantFetch: falling back to yfinance for company info of %s", ticker)
            return self._fallback().get_company_info(ticker)

        try:
            item = data["data"]
            return CompanyInfo(
                ticker=ticker,
                name=str(item.get("name", ticker)),
                cik=str(item.get("cik", "")),
                sector=str(item.get("sector", "")),
                industry=str(item.get("industry", "")),
                market_cap=float(item.get("market_cap", 0) or 0),
            )
        except (KeyError, ValueError, TypeError) as exc:
            logger.error("QuantFetch: company info parse error for %s: %s", ticker, exc)
            return self._fallback().get_company_info(ticker)

    def close(self):
        """Close the underlying httpx client."""
        self._client.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
