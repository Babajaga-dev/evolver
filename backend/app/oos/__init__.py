"""Out-of-sample validation — train/test split per il GA.

Workflow:
    1. L'utente lancia un GA normale su periodo X (training period)
    2. Quando completato, chiama validate_oos(population_id, test_days)
    3. Il runner prende le top-K strategie dal Pareto del GA
    4. Per ogni strategia: backtest su (train_end → train_end + test_days)
    5. Calcola degradation = sharpe_test / sharpe_train, verdict per strategia,
       verdict aggregato per la popolazione

Verdetti:
    - robust: ≥60% delle strategie ha sharpe_test > 0 e degradation > 0.5
    - mixed: 30-60% delle strategie passa il check
    - overfit: <30% — il GA ha memorizzato il train period
"""

from app.oos.runner import (
    OosError,
    OosResult,
    OosStrategyResult,
    validate_oos,
)

__all__ = [
    "OosError",
    "OosResult",
    "OosStrategyResult",
    "validate_oos",
]
