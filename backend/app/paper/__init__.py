"""Paper trading — tracking simulato di posizioni e P&L.

Slice 4.0a: scaffold read-only (repository + endpoints).
Slice 4.0b: engine tick-by-tick che genera trade da segnali GA.
"""

from app.paper.engine import PaperEngineConfig, run_engine_tick
from app.paper.repository import (
    create_initial_snapshot,
    get_paper_state,
    list_equity_curve,
    list_paper_trades,
)

__all__ = [
    "PaperEngineConfig",
    "create_initial_snapshot",
    "get_paper_state",
    "list_equity_curve",
    "list_paper_trades",
    "run_engine_tick",
]
