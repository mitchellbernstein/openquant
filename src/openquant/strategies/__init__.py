"""Built-in trading strategies for OpenQuant."""

from openquant.strategies.base import BaseStrategy, StrategyResult, BacktestResult
from openquant.strategies.insider_momentum import InsiderMomentumStrategy
from openquant.strategies.value_deep import ValueDeepStrategy
from openquant.strategies.earnings_surge import EarningsSurgeStrategy
from openquant.strategies.technical_breakout import TechnicalBreakoutStrategy

__all__ = [
    "BaseStrategy",
    "StrategyResult",
    "BacktestResult",
    "InsiderMomentumStrategy",
    "ValueDeepStrategy",
    "EarningsSurgeStrategy",
    "TechnicalBreakoutStrategy",
]
