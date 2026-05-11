"""Cash-and-Carry funding arbitrage — market-neutral strategy.

Idea: i perpetual futures pagano un funding rate ogni 8 ore. Quando il funding
è positivo, i long pagano i short. Una posizione market-neutral che catturi
questo funding è:

    LONG  spot N coin
    SHORT perp N coin
    -> esposizione direzionale netta = 0
    -> guadagno = N × funding_rate × prezzo ad ogni stacco (ogni 8h)
    -> costo  = fee entry/exit + slippage + funding di breakeven

Sharpe documentato (He & Manela 2024, arXiv 2212.06888):
    1.8 per retail con fee 6 bps round-trip
    3.5 per market maker con zero fee

Quando entrare: funding > entry_threshold per >= N stacchi consecutivi
Quando uscire:  funding < exit_threshold per >= M stacchi consecutivi
"""
from app.carry.engine import run_cash_and_carry, CarryConfig, CarryResult
__all__ = ["run_cash_and_carry", "CarryConfig", "CarryResult"]
