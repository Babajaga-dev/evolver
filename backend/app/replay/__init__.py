"""Replay engine — organismo evolutivo adattivo su dati storici.

Componenti:
- council.py:  Council multi-indicator × multi-TF (4 ind × 3 TF + regime gate)
- genome.py:   Encoder/decoder cromosoma per il Council
- organism.py: Stato attivo (params correnti + decisione)
- runner.py:   Loop temporale, retrain trigger, kill switch, persistenza DB
- repo.py:     Repository CRUD per replay_runs / events / snapshots
- baselines.py: Backtest dei 3 baseline (buy&hold, textbook RSI, GA-one-shot)
"""
from app.replay.runner import ReplayRunner  # noqa: F401
