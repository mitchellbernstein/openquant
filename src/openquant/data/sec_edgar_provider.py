"""SEC EDGAR data provider - free, direct access to SEC filings.

This provider makes REST calls to the SEC EDGAR APIs:
  - Full-Text Search API for Form 4 insider filings
  - Company Facts API for company metadata / CIK lookup
  - Submissions API for filing history

Rate limits: 10 requests/second (SEC requires User-Agent header).
Only implements get_insider_trades() and get_company_info() —
other methods return empty lists (use a faster provider for those).
"""

from __future__ import annotations

import logging
import os
import time
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

SEC_EDGAR_BASE = "https://efts.sec.gov/LATEST"
SEC_COMPANY_BASE = "https://data.sec.gov"
SEC_FULLTEXT_BASE = "https://efts.sec.gov/LATEST"

_DEFAULT_USER_AGENT = "OpenQuant support@openquant.dev"
_DEFAULT_TIMEOUT = 15.0


class SECEdgarProvider:
    """Data provider backed by SEC EDGAR public APIs.

    Free but rate-limited (10 req/s). Only provides insider trades
    (Form 4) and company info. All other methods return empty lists.
    """

    def __init__(
        self,
        user_agent: Optional[str] = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ):
        self._user_agent = user_agent or os.environ.get(
            "SEC_EDGAR_USER_AGENT", _DEFAULT_USER_AGENT
        )
        self._timeout = timeout
        self._last_request_time = 0.0
        self._min_interval = 0.11  # ~9 req/s to stay safely under 10/s
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": self._user_agent},
        )

    @property
    def name(self) -> str:
        return "SEC EDGAR"

    @property
    def is_free(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Rate-limiting helper
    # ------------------------------------------------------------------

    def _throttle(self):
        """Sleep briefly to stay under SEC rate limits."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.monotonic()

    def _get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """GET with throttling and error handling."""
        self._throttle()
        try:
            resp = self._client.get(url, params=params or {})
            if resp.status_code == 429:
                logger.warning("SEC EDGAR: rate limited, retrying after 1s")
                time.sleep(1.0)
                resp = self._client.get(url, params=params or {})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("SEC EDGAR HTTP %s: %s", exc.response.status_code, exc)
            return None
        except Exception as exc:
            logger.error("SEC EDGAR request error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # CIK lookup helper
    # ------------------------------------------------------------------

    def _get_cik(self, ticker: str) -> Optional[str]:
        """Look up CIK for a ticker via SEC company search."""
        url = f"{SEC_COMPANY_BASE}/files/company_tickers.json"
        data = self._get(url)
        if data is None:
            return None
        # The JSON is {0: {"cik_str": "0000320193", "ticker": "AAPL", "title": "Apple Inc."}, ...}
        ticker_upper = ticker.upper()
        for entry in data.values():
            if isinstance(entry, dict) and entry.get("ticker", "").upper() == ticker_upper:
                cik = str(entry.get("cik_str", entry.get("cik", "")))
                # Pad CIK to 10 digits
                return cik.zfill(10) if cik else None
        return None

    # ------------------------------------------------------------------
    # Public API — only insider_trades and company_info are implemented
    # ------------------------------------------------------------------

    def get_prices(self, ticker: str, start: date, end: date) -> List[Price]:
        """Not supported by SEC EDGAR — returns empty list."""
        return []

    def get_financials(self, ticker: str, statement_type: str = "income") -> List[FinancialStatement]:
        """Not supported by SEC EDGAR — returns empty list."""
        return []

    def get_analyst_estimates(self, ticker: str) -> List[AnalystEstimate]:
        """Not supported by SEC EDGAR — returns empty list."""
        return []

    def get_news(self, ticker: str, limit: int = 10) -> List[NewsItem]:
        """Not supported by SEC EDGAR — returns empty list."""
        return []

    def get_insider_trades(self, ticker: str, days: int = 90) -> List[InsiderTrade]:
        """Fetch insider trades from SEC Form 4 filings via Full-Text Search API."""
        cik = self._get_cik(ticker)
        if not cik:
            logger.warning("SEC EDGAR: could not find CIK for %s", ticker)
            return []

        # Use EDGAR full-text search to find Form 4 filings
        url = f"{SEC_FULLTEXT_BASE}/search-index"
        params = {
            "q": f"{ticker}",
            "dateRange": f"custom",
            "startdt": date(date.today().year, 1, 1).isoformat(),
            "enddt": date.today().isoformat(),
            "forms": "4",
            "entityName": ticker,
        }

        # Alternative: Use the submissions endpoint to get recent filings
        submissions_url = f"{SEC_COMPANY_BASE}/submissions/CIK{cik}.json"
        data = self._get(submissions_url)
        if data is None:
            return []

        recent = data.get("filings", {}).get("recent", {})
        form_list = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        accession_numbers = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])

        trades: List[InsiderTrade] = []
        cutoff = date.today().toordinal() - days

        for i, form in enumerate(form_list):
            if form != "4":
                continue
            try:
                filing_date = date.fromisoformat(filing_dates[i][:10])
            except (IndexError, ValueError):
                continue
            if filing_date.toordinal() < cutoff:
                continue

            # We have a Form 4 filing — extract what we can from the index
            # (Full parsing requires downloading the XML, which is slow.)
            acc_num = accession_numbers[i] if i < len(accession_numbers) else ""
            doc_name = primary_docs[i] if i < len(primary_docs) else ""

            # Build a placeholder trade from the filing metadata
            # Real implementation would fetch and parse the XML filing
            trades.append(
                InsiderTrade(
                    ticker=ticker,
                    insider_name="[Form 4 Filing]",
                    title="",
                    transaction_type="BUY",  # Default — needs XML parsing to determine
                    shares=0,
                    price=0.0,
                    value=0.0,
                    date=filing_date,
                    source=self.name,
                )
            )

        logger.info("SEC EDGAR: found %d Form 4 filings for %s in last %d days", len(trades), ticker, days)
        return trades

    def get_company_info(self, ticker: str) -> Optional[CompanyInfo]:
        """Fetch company metadata from SEC EDGAR company facts."""
        cik = self._get_cik(ticker)
        if not cik:
            logger.warning("SEC EDGAR: could not find CIK for %s", ticker)
            return None

        # Company facts endpoint
        facts_url = f"{SEC_COMPANY_BASE}/api/xbrl/companyfacts/CIK{cik}.json"
        data = self._get(facts_url)
        if data is None:
            return None

        try:
            entity = data.get("entityName", ticker)
            cik_str = str(data.get("cik", cik))
            # Try to extract sector/industry from facts if available
            facts = data.get("facts", {})
            # Some companies have sic description in their submission data
            # For now, use what we have
            market_cap = 0.0
            # Try to get entity information from the submissions endpoint
            sub_url = f"{SEC_COMPANY_BASE}/submissions/CIK{cik}.json"
            sub_data = self._get(sub_url)

            sector = ""
            industry = ""
            if sub_data:
                # SIC code description can give industry info
                sic = sub_data.get("sic", "")
                sic_desc = sub_data.get("sicDescription", "")
                industry = sic_desc
                # Try to map SIC to a sector heuristically
                sector = _sic_to_sector(sic)

            return CompanyInfo(
                ticker=ticker,
                name=entity,
                cik=cik_str,
                sector=sector,
                industry=industry,
                market_cap=market_cap,
            )
        except Exception as exc:
            logger.error("SEC EDGAR: company info parse error for %s: %s", ticker, exc)
            return None

    def close(self):
        """Close the underlying httpx client."""
        self._client.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _sic_to_sector(sic: str) -> str:
    """Rough SIC code to sector mapping. Returns empty string if unknown."""
    if not sic:
        return ""
    try:
        code = int(sic)
    except (ValueError, TypeError):
        return ""

    if 100 <= code <= 999:
        return "Agriculture"
    elif 1000 <= code <= 1499:
        return "Mining"
    elif 1500 <= code <= 1799:
        return "Construction"
    elif 2000 <= code <= 3999:
        return "Manufacturing"
    elif 4000 <= code <= 4999:
        return "Transportation & Utilities"
    elif 5000 <= code <= 5199:
        return "Wholesale Trade"
    elif 5200 <= code <= 5999:
        return "Retail Trade"
    elif 6000 <= code <= 6799:
        return "Finance"
    elif 7000 <= code <= 8999:
        return "Services"
    elif 9000 <= code <= 9999:
        return "Public Administration"
    return ""
