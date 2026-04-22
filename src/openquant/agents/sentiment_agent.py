"""Sentiment analysis agent — keyword-based news sentiment.

Evaluates stocks based on recent news headlines using simple
keyword matching. No LLM required for the basic version.

The keyword lists are curated from financial news analysis research.
Positive/negative word counts are weighted and combined into a signal.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from openquant.agents.base import BaseAgent, SignalResult
from openquant.data.resolver import DataResolver

logger = logging.getLogger(__name__)

# ── Sentiment keyword lists ──────────────────────────────────────────

POSITIVE_WORDS = frozenset({
    "surge", "soar", "rally", "gain", "profit", "beat", "exceed", "boost",
    "growth", "upgrade", "bullish", "outperform", "rise", "jump", "climb",
    "record", "high", "strong", "positive", "optimistic", "innovate",
    "breakthrough", "expand", "acquisition", "partnership", "launch",
    "dividend", "buyback", "repurchase", "upside", "momentum", "recover",
    "resilient", "robust", "thrive", "accelerate", "outpace", "dominate",
})

NEGATIVE_WORDS = frozenset({
    "crash", "plunge", "drop", "fall", "loss", "miss", "cut", "downgrade",
    "bearish", "underperform", "decline", "slump", "tumble", "dive",
    "bankrupt", "debt", "default", "lawsuit", "investigation", "fraud",
    "sec", "fined", "penalty", "recall", "layoff", "fired", "resign",
    "scandal", "crisis", "warning", "weak", "negative", "pessimistic",
    "shrink", "contract", "implode", "collapse", "bleed", "hemorrhage",
})

INTENSIFIERS = frozenset({
    "sharply", "steeply", "dramatically", "significantly", "massively",
    "heavily", "deeply", "severely", "urgently", "critically",
})


class SentimentAgent(BaseAgent):
    """Analyzes stocks using keyword-based news sentiment.

    Scans recent news headlines for positive/negative financial keywords.
    Weights by recency and intensity. No LLM needed.
    """

    name = "sentiment"
    description = "Sentiment agent — keyword-based news sentiment analysis"

    def analyze(self, ticker: str, data: DataResolver) -> SignalResult:
        metrics: Dict[str, Any] = {}
        reasons: List[str] = []

        try:
            news = data.get_news(ticker, limit=25)
        except Exception as exc:
            logger.debug("SentimentAgent: news fetch failed for %s: %s", ticker, exc)
            news = []

        if not news:
            return SignalResult(
                agent_name=self.name,
                ticker=ticker,
                signal=0.0,
                confidence=10,
                reasoning="No recent news found for sentiment analysis.",
                data=metrics,
            )

        # ── Score each headline ────────────────────────────────────
        total_positive = 0
        total_negative = 0
        article_scores: List[float] = []

        for item in news:
            headline = (item.title + " " + item.summary).lower() if item.summary else item.title.lower()
            words = set(re.findall(r"[a-z]+", headline))

            pos_hits = words & POSITIVE_WORDS
            neg_hits = words & NEGATIVE_WORDS
            intensifier_hits = words & INTENSIFIERS

            # Intensifiers multiply the weight of matched words
            multiplier = 1.5 if intensifier_hits else 1.0

            pos_score = len(pos_hits) * multiplier
            neg_score = len(neg_hits) * multiplier

            total_positive += pos_score
            total_negative += neg_score

            # Per-article score: [-1, +1]
            if pos_score + neg_score > 0:
                article_scores.append((pos_score - neg_score) / (pos_score + neg_score))
            else:
                article_scores.append(0.0)

        # ── Aggregate ──────────────────────────────────────────────
        if not article_scores:
            avg_score = 0.0
        else:
            # Weight recent articles more (they come first from the provider)
            weights = [1.0 / (1 + 0.1 * i) for i in range(len(article_scores))]
            total_weight = sum(weights)
            avg_score = sum(s * w for s, w in zip(article_scores, weights)) / total_weight

        # Scale to signal range — keyword sentiment is noisy, so dampen
        signal = round(avg_score * 0.7, 3)

        metrics["articles_analyzed"] = len(news)
        metrics["positive_keywords"] = total_positive
        metrics["negative_keywords"] = total_negative
        metrics["net_sentiment"] = round(avg_score, 3)

        if total_positive > total_negative * 2:
            reasons.append(f"Overwhelmingly positive news sentiment ({total_positive} vs {total_negative} keywords)")
        elif total_negative > total_positive * 2:
            reasons.append(f"Overwhelmingly negative news sentiment ({total_negative} vs {total_positive} keywords)")
        elif total_positive > total_negative:
            reasons.append(f"Mildly positive news sentiment ({total_positive} vs {total_negative} keywords)")
        elif total_negative > total_positive:
            reasons.append(f"Mildly negative news sentiment ({total_negative} vs {total_positive} keywords)")
        else:
            reasons.append(f"Neutral news sentiment ({total_positive} positive, {total_negative} negative keywords)")

        # Confidence based on number of articles
        confidence = min(60, len(news) * 5)

        return SignalResult(
            agent_name=self.name,
            ticker=ticker,
            signal=signal,
            confidence=confidence,
            reasoning="; ".join(reasons),
            data=metrics,
        )
