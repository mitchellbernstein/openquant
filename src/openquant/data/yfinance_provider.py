"""YFinance data provider - free market data via yfinance library."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import List, Optional, Dict, Any

import yfinance as yf
import pandas as pd

from openquant.data.protocol import (
    Price,
    InsiderTrade,
    FinancialStatement,
    AnalystEstimate,
    NewsItem,
    CompanyInfo,
)

logger = logging.getLogger(__name__)


class YFinanceProvider:
    """Data provider backed by the yfinance library.

    Free, no API key required. Subject to Yahoo Finance rate limits
    and data availability constraints.
    """

    @property
    def name(self) -> str:
        return "yfinance"

    @property
    def is_free(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_prices(self, ticker: str, start: date, end: date) -> List[Price]:
        """Fetch historical OHLCV prices via yfinance Ticker.history()."""
        try:
            t = yf.Ticker(ticker)
            df = t.history(start=start.isoformat(), end=end.isoformat(), auto_adjust=True)
            if df is None or df.empty:
                logger.warning("yfinance: no price data for %s (%s to %s)", ticker, start, end)
                return []

            prices: List[Price] = []
            for idx, row in df.iterrows():
                # yfinance returns Timestamp index; convert to date
                row_date = idx.date() if hasattr(idx, "date") else idx
                prices.append(
                    Price(
                        ticker=ticker,
                        date=row_date,
                        open=_safe_float(row.get("Open")),
                        high=_safe_float(row.get("High")),
                        low=_safe_float(row.get("Low")),
                        close=_safe_float(row.get("Close")),
                        volume=int(_safe_float(row.get("Volume"), default=0)),
                        source=self.name,
                    )
                )
            return prices

        except Exception as exc:
            logger.error("yfinance get_prices error for %s: %s", ticker, exc)
            return []

    def get_insider_trades(self, ticker: str, days: int = 90) -> List[InsiderTrade]:
        """Fetch insider transactions via yfinance Ticker.insider_transactions."""
        try:
            t = yf.Ticker(ticker)
            df = t.insider_transactions
            if df is None or (hasattr(df, "empty") and df.empty):
                # Fallback: try insider_purchases / insider_roster_holders
                logger.debug("yfinance: no insider_transactions for %s, trying purchases", ticker)
                df = t.insider_purchases
            if df is None or (hasattr(df, "empty") and df.empty):
                logger.warning("yfinance: no insider data for %s", ticker)
                return []

            trades: List[InsiderTrade] = []
            for _, row in df.iterrows():
                row_date = _parse_yf_date(row.get("Start Date") or row.get("Date"))
                if row_date is None:
                    continue

                # yfinance columns vary; try common names
                shares = int(_safe_float(
                    row.get("Shares") or row.get("Transaction Shares"), default=0
                ))
                price = _safe_float(
                    row.get("Price") or row.get("Transaction Price per Share"), default=0.0
                )
                value = _safe_float(
                    row.get("Value") or row.get("Transaction Value"), default=0.0
                )
                txn_type = str(
                    row.get("Transaction Type") or row.get("Side") or ""
                ).upper()
                if "PURCHASE" in txn_type or "BUY" in txn_type:
                    txn_type = "BUY"
                elif "SALE" in txn_type or "SELL" in txn_type:
                    txn_type = "SELL"
                else:
                    # Skip if we can't classify
                    txn_type = str(row.get("Transaction Type", "UNKNOWN")).upper()

                trades.append(
                    InsiderTrade(
                        ticker=ticker,
                        insider_name=str(row.get("Insider") or row.get("Name") or ""),
                        title=str(row.get("Title") or row.get("Position") or ""),
                        transaction_type=txn_type,
                        shares=shares,
                        price=price,
                        value=value,
                        date=row_date,
                        source=self.name,
                    )
                )
            return trades

        except Exception as exc:
            logger.error("yfinance get_insider_trades error for %s: %s", ticker, exc)
            return []

    def get_financials(
        self, ticker: str, statement_type: str = "income"
    ) -> List[FinancialStatement]:
        """Fetch financial statements via yfinance Ticker financials."""
        try:
            t = yf.Ticker(ticker)
            # Map statement_type to yfinance attribute
            attr_map = {
                "income": "financials",
                "balance": "balance_sheet",
                "cashflow": "cashflow",
            }
            attr = attr_map.get(statement_type, "financials")
            df = getattr(t, attr, None)
            if df is None or (hasattr(df, "empty") and df.empty):
                logger.warning("yfinance: no %s financials for %s", statement_type, ticker)
                return []

            statements: List[FinancialStatement] = []
            # yfinance financials: rows=metric names, columns=period end dates
            for col in df.columns:
                period_date = _parse_yf_date(col)
                if period_date is None:
                    period_date = date.today()
                items: Dict[str, Any] = {}
                for idx, val in df[col].items():
                    if pd.notna(val):
                        items[str(idx)] = float(val) if not isinstance(val, str) else val

                statements.append(
                    FinancialStatement(
                        ticker=ticker,
                        statement_type=statement_type,
                        period="annual",
                        period_end_date=period_date,
                        items=items,
                        source=self.name,
                    )
                )
            return statements

        except Exception as exc:
            logger.error("yfinance get_financials error for %s: %s", ticker, exc)
            return []

    def get_analyst_estimates(self, ticker: str) -> List[AnalystEstimate]:
        """Fetch analyst consensus estimates via yfinance earnings/revenue estimates."""
        estimates: List[AnalystEstimate] = []
        try:
            t = yf.Ticker(ticker)

            # EPS estimates
            eps_df = t.earnings_estimate
            if eps_df is not None and not eps_df.empty:
                for period_key, row in eps_df.iterrows():
                    estimates.append(
                        AnalystEstimate(
                            ticker=ticker,
                            estimate_type="eps",
                            period=str(period_key),
                            consensus_avg=_safe_float(row.get("avg"), default=0.0),
                            consensus_low=_safe_float(row.get("low"), default=0.0),
                            consensus_high=_safe_float(row.get("high"), default=0.0),
                            number_of_analysts=int(_safe_float(row.get("numberOfAnalysts"), default=0)),
                            source=self.name,
                        )
                    )

            # Revenue estimates
            rev_df = t.revenue_estimate
            if rev_df is not None and not rev_df.empty:
                for period_key, row in rev_df.iterrows():
                    estimates.append(
                        AnalystEstimate(
                            ticker=ticker,
                            estimate_type="revenue",
                            period=str(period_key),
                            consensus_avg=_safe_float(row.get("avg"), default=0.0),
                            consensus_low=_safe_float(row.get("low"), default=0.0),
                            consensus_high=_safe_float(row.get("high"), default=0.0),
                            number_of_analysts=int(_safe_float(row.get("numberOfAnalysts"), default=0)),
                            source=self.name,
                        )
                    )

            # Recommendations (price target proxy)
            rec_df = t.recommendations
            if rec_df is not None and not rec_df.empty:
                # Aggregate recommendation counts as a pseudo price-target estimate
                try:
                    latest = rec_df.iloc[-1] if len(rec_df) > 0 else None
                    if latest is not None:
                        # yfinance recommendations have 'strongBuy', 'buy', 'hold', 'sell', 'strongSell'
                        total = sum(
                            int(_safe_float(latest.get(k), default=0))
                            for k in ("strongBuy", "buy", "hold", "sell", "strongSell")
                        )
                        if total > 0:
                            estimates.append(
                                AnalystEstimate(
                                    ticker=ticker,
                                    estimate_type="price_target",
                                    period="current",
                                    consensus_avg=0.0,
                                    consensus_low=0.0,
                                    consensus_high=0.0,
                                    number_of_analysts=total,
                                    source=self.name,
                                )
                            )
                except Exception as exc:
                    logger.debug("yfinance: recommendations parse error: %s", exc)

            return estimates

        except Exception as exc:
            logger.error("yfinance get_analyst_estimates error for %s: %s", ticker, exc)
            return estimates

    def get_news(self, ticker: str, limit: int = 10) -> List[NewsItem]:
        """Fetch recent news via yfinance Ticker.news."""
        try:
            t = yf.Ticker(ticker)
            raw_news = t.news
            if not raw_news:
                logger.warning("yfinance: no news for %s", ticker)
                return []

            items: List[NewsItem] = []
            for entry in raw_news[:limit]:
                # yfinance returns list of dicts
                pub_date = _parse_yf_timestamp(entry.get("publish_time") or entry.get("providerPublishTime"))
                items.append(
                    NewsItem(
                        title=str(entry.get("title", "")),
                        source=str(entry.get("publisher") or entry.get("source", "")),
                        url=str(entry.get("link") or entry.get("url", "")),
                        date=pub_date or datetime.now(),
                        ticker=ticker,
                        summary=str(entry.get("summary") or entry.get("title", "")),
                    )
                )
            return items

        except Exception as exc:
            logger.error("yfinance get_news error for %s: %s", ticker, exc)
            return []

    def get_company_info(self, ticker: str) -> Optional[CompanyInfo]:
        """Fetch company metadata via yfinance Ticker.info."""
        try:
            t = yf.Ticker(ticker)
            info = t.info
            if not info:
                logger.warning("yfinance: no company info for %s", ticker)
                return None

            return CompanyInfo(
                ticker=ticker,
                name=str(info.get("longName") or info.get("shortName") or ticker),
                cik=str(info.get("companyOfficers", "")).strip("[]") if info.get("companyOfficers") else "",
                sector=str(info.get("sector", "")),
                industry=str(info.get("industry", "")),
                market_cap=float(info.get("marketCap", 0) or 0),
            )

        except Exception as exc:
            logger.error("yfinance get_company_info error for %s: %s", ticker, exc)
            return None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _safe_float(value, default: float = 0.0) -> float:
    """Convert a value to float, returning *default* on failure."""
    try:
        if value is None or (isinstance(value, float) and (value != value)):  # NaN check
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_yf_date(val) -> Optional[date]:
    """Parse a date-like value from yfinance (Timestamp, str, datetime)."""
    if val is None:
        return None
    try:
        if hasattr(val, "date"):
            return val.date()
        if isinstance(val, str):
            return date.fromisoformat(val[:10])
        if isinstance(val, (int, float)):
            # Could be epoch seconds
            return datetime.fromtimestamp(val).date()
        if isinstance(val, date):
            return val
    except Exception:
        pass
    return None


def _parse_yf_timestamp(val) -> Optional[datetime]:
    """Parse a timestamp-like value from yfinance."""
    if val is None:
        return None
    try:
        if isinstance(val, datetime):
            return val
        if isinstance(val, (int, float)):
            return datetime.fromtimestamp(val)
        if hasattr(val, "to_pydatetime"):
            return val.to_pydatetime()
    except Exception:
        pass
    return None
