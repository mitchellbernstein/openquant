"""Configuration management for OpenQuant.

Loads from ~/.openquant/config.yaml. Manages broker configs,
API keys (from environment variables), and strategy defaults.

Environment variables take precedence over config file values.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)

# Default config directory
CONFIG_DIR = Path.home() / ".openquant"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


@dataclass
class BrokerConfig:
    """Configuration for a broker connection.

    Attributes:
        name: Broker identifier.
        enabled: Whether this broker is active.
        mode: Execution mode: 'game', 'signal', or 'live'.
        api_key_env: Environment variable name for API key.
        api_secret_env: Environment variable name for API secret.
    """
    name: str
    enabled: bool = False
    mode: str = "game"
    api_key_env: str = ""
    api_secret_env: str = ""


@dataclass
class StrategyDefaults:
    """Default parameters for strategies.

    Attributes:
        default_strategy: Strategy to use when none specified.
        position_size_max: Maximum position size as fraction of portfolio.
        stop_loss_default: Default stop loss percentage.
        take_profit_default: Default take profit percentage.
        confidence_threshold: Minimum confidence to act on a signal.
    """
    default_strategy: str = "insider-momentum"
    position_size_max: float = 0.25
    stop_loss_default: float = 0.05
    take_profit_default: float = 0.15
    confidence_threshold: int = 40


@dataclass
class OpenQuantConfig:
    """Top-level OpenQuant configuration.

    Attributes:
        broker_configs: Broker connection configurations.
        strategy_defaults: Default strategy parameters.
        game_starting_balance: Starting balance for game mode.
        data_provider_priority: Order of data providers to try.
        custom: Arbitrary custom configuration.
    """
    broker_configs: Dict[str, BrokerConfig] = field(default_factory=dict)
    strategy_defaults: StrategyDefaults = field(default_factory=StrategyDefaults)
    game_starting_balance: float = 10000.0
    data_provider_priority: list = field(default_factory=lambda: ["quantfetch", "yfinance", "sec_edgar"])
    custom: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Ensure default broker configs exist
        if "paper" not in self.broker_configs:
            self.broker_configs["paper"] = BrokerConfig(name="paper", enabled=True, mode="game")
        if "alpaca" not in self.broker_configs:
            self.broker_configs["alpaca"] = BrokerConfig(
                name="alpaca", enabled=False, mode="game",
                api_key_env="ALPACA_API_KEY", api_secret_env="ALPACA_SECRET_KEY",
            )
        if "kalshi" not in self.broker_configs:
            self.broker_configs["kalshi"] = BrokerConfig(
                name="kalshi", enabled=False, mode="game",
                api_key_env="KALSHI_API_KEY", api_secret_env="KALSHI_API_SECRET",
            )

    def get_api_key(self, broker_name: str) -> str:
        """Get API key for a broker from environment variable.

        Args:
            broker_name: Broker identifier.

        Returns:
            API key string (empty if not set).
        """
        config = self.broker_configs.get(broker_name)
        if config and config.api_key_env:
            return os.environ.get(config.api_key_env, "")
        # Fallback: check common env vars
        return os.environ.get(f"{broker_name.upper()}_API_KEY", "")

    def get_api_secret(self, broker_name: str) -> str:
        """Get API secret for a broker from environment variable.

        Args:
            broker_name: Broker identifier.

        Returns:
            API secret string (empty if not set).
        """
        config = self.broker_configs.get(broker_name)
        if config and config.api_secret_env:
            return os.environ.get(config.api_secret_env, "")
        return os.environ.get(f"{broker_name.upper()}_API_SECRET", "")


def load(path: Optional[Path] = None) -> OpenQuantConfig:
    """Load configuration from YAML file.

    Creates default config if file doesn't exist.

    Args:
        path: Path to config file (defaults to ~/.openquant/config.yaml).

    Returns:
        OpenQuantConfig instance.
    """
    config_path = path or CONFIG_FILE

    if not config_path.exists():
        logger.info("Config file not found at %s — using defaults", config_path)
        config = OpenQuantConfig()
        # Save defaults for next time
        save(config, config_path)
        return config

    try:
        with open(config_path, "r") as f:
            raw = yaml.safe_load(f) or {}
    except Exception as exc:
        logger.warning("Failed to load config from %s: %s — using defaults", config_path, exc)
        return OpenQuantConfig()

    return _parse_config(raw)


def save(config: OpenQuantConfig, path: Optional[Path] = None) -> None:
    """Save configuration to YAML file.

    Args:
        config: Configuration to save.
        path: Path to config file (defaults to ~/.openquant/config.yaml).
    """
    config_path = path or CONFIG_FILE

    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict
    data = {
        "brokers": {
            name: {
                "enabled": bc.enabled,
                "mode": bc.mode,
                "api_key_env": bc.api_key_env,
                "api_secret_env": bc.api_secret_env,
            }
            for name, bc in config.broker_configs.items()
        },
        "strategy_defaults": {
            "default_strategy": config.strategy_defaults.default_strategy,
            "position_size_max": config.strategy_defaults.position_size_max,
            "stop_loss_default": config.strategy_defaults.stop_loss_default,
            "take_profit_default": config.strategy_defaults.take_profit_default,
            "confidence_threshold": config.strategy_defaults.confidence_threshold,
        },
        "game_starting_balance": config.game_starting_balance,
        "data_provider_priority": config.data_provider_priority,
        "custom": config.custom,
    }

    try:
        with open(config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        logger.info("Config saved to %s", config_path)
    except Exception as exc:
        logger.error("Failed to save config to %s: %s", config_path, exc)


def _parse_config(raw: Dict[str, Any]) -> OpenQuantConfig:
    """Parse raw YAML dict into OpenQuantConfig."""
    # Parse broker configs
    broker_configs: Dict[str, BrokerConfig] = {}
    for name, bc_data in raw.get("brokers", {}).items():
        broker_configs[name] = BrokerConfig(
            name=name,
            enabled=bc_data.get("enabled", False),
            mode=bc_data.get("mode", "game"),
            api_key_env=bc_data.get("api_key_env", ""),
            api_secret_env=bc_data.get("api_secret_env", ""),
        )

    # Parse strategy defaults
    sd_data = raw.get("strategy_defaults", {})
    strategy_defaults = StrategyDefaults(
        default_strategy=sd_data.get("default_strategy", "insider-momentum"),
        position_size_max=sd_data.get("position_size_max", 0.25),
        stop_loss_default=sd_data.get("stop_loss_default", 0.05),
        take_profit_default=sd_data.get("take_profit_default", 0.15),
        confidence_threshold=sd_data.get("confidence_threshold", 40),
    )

    return OpenQuantConfig(
        broker_configs=broker_configs,
        strategy_defaults=strategy_defaults,
        game_starting_balance=raw.get("game_starting_balance", 10000.0),
        data_provider_priority=raw.get("data_provider_priority", ["quantfetch", "yfinance", "sec_edgar"]),
        custom=raw.get("custom", {}),
    )
