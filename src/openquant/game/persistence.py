"""Persistence layer for OpenQuant game sessions.

Saves/loads game state as JSON files under ~/.openquant/game/.
Each session is stored as a separate file named by session ID.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Optional

from openquant.game.engine import GameEngine
from openquant.game.models import Position, Achievement, ACHIEVEMENTS

logger = logging.getLogger(__name__)

GAME_DIR = Path.home() / ".openquant" / "game"


def _ensure_game_dir() -> Path:
    """Create the game directory if it doesn't exist."""
    GAME_DIR.mkdir(parents=True, exist_ok=True)
    return GAME_DIR


def new_session_id() -> str:
    """Generate a new session ID."""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    return f"{ts}-{short_id}"


def _serialize_engine(engine: GameEngine, session_id: str, strategy: str) -> dict:
    """Serialize a GameEngine to a JSON-compatible dict."""
    # Convert trading_days set to sorted list of ISO strings
    trading_days = engine.stats.get("trading_days", set())
    if isinstance(trading_days, set):
        trading_days = sorted(d.isoformat() if isinstance(d, date) else str(d) for d in trading_days)
    else:
        trading_days = []

    positions = {}
    for ticker, pos in engine.positions.items():
        positions[ticker] = {
            "ticker": pos.ticker,
            "shares": pos.shares,
            "avg_price": pos.avg_price,
            "current_price": pos.current_price,
            "held_since": pos.held_since.isoformat() if pos.held_since else None,
        }

    achievements = {}
    for name, ach in engine.achievements.items():
        achievements[name] = {
            "name": ach.name,
            "title": ach.title,
            "description": ach.description,
            "icon": ach.icon,
            "unlocked_at": ach.unlocked_at.isoformat() if ach.unlocked_at else None,
        }

    return {
        "session_id": session_id,
        "strategy": strategy,
        "starting_balance": engine.starting_balance,
        "balance": engine.balance,
        "positions": positions,
        "trade_history": engine.trade_history,
        "stats": {
            "wins": engine.stats.get("wins", 0),
            "losses": engine.stats.get("losses", 0),
            "total_pnl": engine.stats.get("total_pnl", 0.0),
            "trading_days": trading_days,
        },
        "achievements": achievements,
        "saved_at": datetime.now().isoformat(),
    }


def _deserialize_engine(data: dict) -> tuple[GameEngine, str, str]:
    """Deserialize a dict back into a GameEngine, returning (engine, session_id, strategy)."""
    engine = GameEngine(starting_balance=data["starting_balance"])
    engine.balance = data["balance"]

    # Restore positions
    for ticker, pdata in data.get("positions", {}).items():
        held_since = None
        if pdata.get("held_since"):
            held_since = datetime.fromisoformat(pdata["held_since"])
        engine.positions[ticker] = Position(
            ticker=pdata["ticker"],
            shares=pdata["shares"],
            avg_price=pdata["avg_price"],
            current_price=pdata["current_price"],
            held_since=held_since,
        )

    # Restore trade history
    engine.trade_history = data.get("trade_history", [])

    # Restore stats
    raw_stats = data.get("stats", {})
    trading_days = raw_stats.get("trading_days", [])
    if isinstance(trading_days, list):
        trading_days = {
            date.fromisoformat(d) if "-" in d and "T" not in d else d
            for d in trading_days
        }
    engine.stats = {
        "wins": raw_stats.get("wins", 0),
        "losses": raw_stats.get("losses", 0),
        "total_pnl": raw_stats.get("total_pnl", 0.0),
        "trading_days": trading_days,
    }

    # Restore achievements
    for name, adata in data.get("achievements", {}).items():
        if name in engine.achievements:
            unlocked_at = None
            if adata.get("unlocked_at"):
                unlocked_at = datetime.fromisoformat(adata["unlocked_at"])
            engine.achievements[name].unlocked_at = unlocked_at

    session_id = data["session_id"]
    strategy = data.get("strategy", "unknown")
    return engine, session_id, strategy


def save_session(engine: GameEngine, session_id: str, strategy: str) -> Path:
    """Save a game session to disk."""
    _ensure_game_dir()
    data = _serialize_engine(engine, session_id, strategy)
    path = GAME_DIR / f"{session_id}.json"
    path.write_text(json.dumps(data, indent=2, default=str))
    logger.debug("Saved session %s to %s", session_id, path)
    return path


def load_session(session_id: str) -> Optional[tuple[GameEngine, str]]:
    """Load a game session from disk. Returns (engine, strategy) or None."""
    path = GAME_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    engine, sid, strategy = _deserialize_engine(data)
    return engine, strategy


def get_active_session_id() -> Optional[str]:
    """Get the most recent session ID (active session)."""
    if not GAME_DIR.exists():
        return None
    json_files = sorted(GAME_DIR.glob("*.json"))
    if not json_files:
        return None
    # Return the most recent by filename (they start with timestamp)
    return json_files[-1].stem


def list_sessions() -> list[dict]:
    """List all saved sessions with basic info."""
    if not GAME_DIR.exists():
        return []
    sessions = []
    for path in sorted(GAME_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            sessions.append({
                "session_id": data["session_id"],
                "strategy": data.get("strategy", "unknown"),
                "starting_balance": data["starting_balance"],
                "balance": data["balance"],
                "saved_at": data.get("saved_at", ""),
            })
        except (json.JSONDecodeError, KeyError):
            continue
    return sessions
