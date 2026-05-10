"""Paper trading — tracking simulato di posizioni e P&L.

Slice 4.0a: scaffold read-only. Il paper engine che GENERA i trade
arriverà in slice successiva. Per ora qui esponiamo solo lo stato
del DB (paper_trades + equity_snapshots).
"""

from app.paper.repository import (
    create_initial_snapshot,
    get_paper_state,
    list_equity_curve,
    list_paper_trades,
)

__all__ = [
    "create_initial_snapshot",
    "get_paper_state",
    "list_equity_curve",
    "list_paper_trades",
]
