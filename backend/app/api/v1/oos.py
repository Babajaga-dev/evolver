"""Endpoint /api/v1/oos — out-of-sample validation."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.logging import get_logger
from app.oos import OosError, validate_oos
from app.schemas.oos import (
    OosBaselineOut,
    OosEvolutionPointOut,
    OosResultResponse,
    OosStrategyOut,
    OosValidateRequest,
)

router = APIRouter(tags=["oos"], prefix="/oos")
log = get_logger(__name__)


@router.post("/validate", response_model=OosResultResponse)
async def oos_validate(
    body: OosValidateRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> OosResultResponse:
    """Valida un GA completato sul periodo successivo (out-of-sample test).

    Workflow:
        1. L'utente lancia un GA normale (1 anno di training)
        2. Quando completed, chiama questo endpoint con population_id + test_days
        3. Il backend prende le top-K strategie del Pareto e le testa sul
           periodo successivo (es. 90 giorni dopo train_end)
        4. Output: tabella con sharpe_train vs sharpe_test, degradation,
           verdetto per strategia + verdetto aggregato
    """
    try:
        result = await validate_oos(
            session,
            population_id=body.population_id,
            test_days=body.test_days,
            top_k=body.top_k,
            initial_cash=body.initial_cash,
            test_start_days_ago=body.test_start_days_ago,
            test_end_days_ago=body.test_end_days_ago,
        )
    except OosError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return OosResultResponse(
        population_id=result.population_id,
        strategy_id=result.strategy_id,
        symbol=result.symbol,
        timeframe=result.timeframe,
        train_start=result.train_start,
        train_end=result.train_end,
        test_start=result.test_start,
        test_end=result.test_end,
        test_days=result.test_days,
        top_k=result.top_k,
        initial_cash=result.initial_cash,
        evolution_curve=[
            OosEvolutionPointOut(
                generation=p.generation,
                best_sharpe_robust_train=p.best_sharpe_robust_train,
                mean_sharpe_robust_train=p.mean_sharpe_robust_train,
                diversity=p.diversity,
                best_sharpe_test=p.best_sharpe_test,
                best_total_return_test=p.best_total_return_test,
                best_n_trades_test=p.best_n_trades_test,
            )
            for p in result.evolution_curve
        ],
        strategies=[
            OosStrategyOut(
                rank=s.rank,
                chromosome=s.chromosome,
                sharpe_train=s.sharpe_train,
                max_drawdown_train=s.max_drawdown_train,
                n_trades_train=s.n_trades_train,
                sharpe_test=s.sharpe_test,
                total_return_test=s.total_return_test,
                max_drawdown_test=s.max_drawdown_test,
                n_trades_test=s.n_trades_test,
                win_rate_test=s.win_rate_test,
                final_equity_test=s.final_equity_test,
                degradation_pct=s.degradation_pct,
                alpha_vs_baseline=s.alpha_vs_baseline,
                verdict=s.verdict,
                verdict_reason=s.verdict_reason,
            )
            for s in result.strategies
        ],
        baseline=(
            OosBaselineOut(
                chromosome=result.baseline.chromosome,
                sharpe_test=result.baseline.sharpe_test,
                total_return_test=result.baseline.total_return_test,
                max_drawdown_test=result.baseline.max_drawdown_test,
                n_trades_test=result.baseline.n_trades_test,
                win_rate_test=result.baseline.win_rate_test,
                final_equity_test=result.baseline.final_equity_test,
            )
            if result.baseline is not None
            else None
        ),
        overall_verdict=result.overall_verdict,
        overall_reason=result.overall_reason,
        n_robust=result.n_robust,
        n_mixed=result.n_mixed,
        n_overfit=result.n_overfit,
        n_no_signal=result.n_no_signal,
        n_alpha_positive=result.n_alpha_positive,
    )
