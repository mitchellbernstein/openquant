"""Local storage for OpenQuant.

Stores trade history, positions, and strategy results in ~/.openquant/.
- JSONL format for trade history (append-only)
- YAML for config and positions
- JSON for strategy results

All storage is local — no data leaves the machine.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# Storage directory
STORAGE_DIR = Path.home() / ".openquant"
TRADES_FILE = STORAGE_DIR / "trades.jsonl"
POSITIONS_FILE = STORAGE_DIR / "positions.yaml"
STRATEGIES_DIR = STORAGE_DIR / "strategies"
STATE_FILE = STORAGE_DIR / "state.yaml"


def _ensure_dir() -> None:
    """Ensure the storage directory exists."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)


# ── Trade history (JSONL append-only) ──────────────────────────────

def save_trade(trade: Dict[str, Any]) -> None:
    """Append a trade record to the JSONL trade log.

    Args:
        trade: Trade data dict. Must include at minimum: action, ticker, shares, price.
    """
    _ensure_dir()

    # Add timestamp if not present
    if "timestamp" not in trade:
        trade["timestamp"] = datetime.now().isoformat()

    try:
        with open(TRADES_FILE, "a") as f:
            f.write(json.dumps(trade, default=str) + "\n")
    except Exception as exc:
        logger.error("Failed to save trade: %s", exc)


def load_trades(limit: int = 0) -> List[Dict[str, Any]]:
    """Load trade history from JSONL file.

    Args:
        limit: Maximum number of trades to return. 0 = all.

    Returns:
        List of trade dicts, most recent last.
    """
    if not TRADES_FILE.exists():
        return []

    trades = []
    try:
        with open(TRADES_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        trades.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("Skipping malformed trade record")
    except Exception as exc:
        logger.error("Failed to load trades: %s", exc)

    if limit > 0 and len(trades) > limit:
        return trades[-limit:]
    return trades


# ── Positions (YAML) ───────────────────────────────────────────────

def save_positions(positions: Dict[str, Dict[str, Any]]) -> None:
    """Save current positions to YAML file.

    Args:
        positions: Dict of ticker -> position data.
    """
    _ensure_dir()
    try:
        with open(POSITIONS_FILE, "w") as f:
            yaml.dump(positions, f, default_flow_style=False, sort_keys=False)
    except Exception as exc:
        logger.error("Failed to save positions: %s", exc)


def load_positions() -> Dict[str, Dict[str, Any]]:
    """Load positions from YAML file.

    Returns:
        Dict of ticker -> position data.
    """
    if not POSITIONS_FILE.exists():
        return {}

    try:
        with open(POSITIONS_FILE, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:
        logger.error("Failed to load positions: %s", exc)
        return {}


# ── Strategy results ──────────────────────────────────────────────

def save_strategy(name: str, data: Dict[str, Any]) -> None:
    """Save a strategy result or configuration.

    Args:
        name: Strategy name (used as filename).
        data: Strategy data to save.
    """
    _ensure_dir()
    filepath = STRATEGIES_DIR / f"{name}.json"
    try:
        with open(filepath, "w") as f:
            json.dump(data, f, default=str, indent=2)
    except Exception as exc:
        logger.error("Failed to save strategy %s: %s", name, exc)


def load_strategies() -> Dict[str, Dict[str, Any]]:
    """Load all saved strategy results.

    Returns:
        Dict of strategy_name -> strategy data.
    """
    if not STRATEGIES_DIR.exists():
        return {}

    strategies = {}
    for filepath in STRATEGIES_DIR.glob("*.json"):
        name = filepath.stem
        try:
            with open(filepath, "r") as f:
                strategies[name] = json.load(f)
        except Exception as exc:
            logger.warning("Failed to load strategy %s: %s", name, exc)

    return strategies


def load_strategy(name: str) -> Optional[Dict[str, Any]]:
    """Load a specific strategy result.

    Args:
        name: Strategy name.

    Returns:
        Strategy data dict, or None if not found.
    """
    filepath = STRATEGIES_DIR / f"{name}.json"
    if not filepath.exists():
        return None

    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception as exc:
        logger.error("Failed to load strategy %s: %s", name, exc)
        return None


# ── Game state (YAML) ──────────────────────────────────────────────

def save_state(state: Dict[str, Any]) -> None:
    """Save game engine state (balance, positions, etc.).

    Args:
        state: Game state dict.
    """
    _ensure_dir()
    try:
        with open(STATE_FILE, "w") as f:
            yaml.dump(state, f, default_flow_style=False, sort_keys=False)
    except Exception as exc:
        logger.error("Failed to save state: %s", exc)


def load_state() -> Dict[str, Any]:
    """Load game engine state.

    Returns:
        Game state dict, or empty dict if not found.
    """
    if not STATE_FILE.exists():
        return {}

    try:
        with open(STATE_FILE, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:
        logger.error("Failed to load state: %s", exc)
        return {}


# ── Utility ────────────────────────────────────────────────────────

def get_storage_path() -> Path:
    """Get the storage directory path."""
    return STORAGE_DIR


def clear_all() -> None:
    """Clear all stored data. Use with caution."""
    for filepath in [TRADES_FILE, POSITIONS_FILE, STATE_FILE]:
        if filepath.exists():
            filepath.unlink()
    if STRATEGIES_DIR.exists():
        for f in STRATEGIES_DIR.glob("*.json"):
            f.unlink()
