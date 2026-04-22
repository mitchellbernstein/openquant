"""Broker integrations for trade execution."""

from openquant.brokers.base import BaseBroker, Position, OrderResult, OrderStatus
from openquant.brokers.paper import PaperBroker

__all__ = [
    "BaseBroker",
    "Position",
    "OrderResult",
    "OrderStatus",
    "PaperBroker",
]

# Optional brokers — only importable when deps are installed
try:
    from openquant.brokers.alpaca import AlpacaBroker
    __all__.append("AlpacaBroker")
except ImportError:
    pass

try:
    from openquant.brokers.kalshi import KalshiBroker
    __all__.append("KalshiBroker")
except ImportError:
    pass
