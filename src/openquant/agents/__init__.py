"""AI Agent framework for OpenQuant."""

from openquant.agents.base import BaseAgent, SignalResult
from openquant.agents.value_agent import ValueInvestingAgent
from openquant.agents.growth_agent import GrowthAgent
from openquant.agents.sentiment_agent import SentimentAgent
from openquant.agents.technical_agent import TechnicalAgent
from openquant.agents.insider_agent import InsiderAgent

__all__ = [
    "BaseAgent",
    "SignalResult",
    "ValueInvestingAgent",
    "GrowthAgent",
    "SentimentAgent",
    "TechnicalAgent",
    "InsiderAgent",
]
