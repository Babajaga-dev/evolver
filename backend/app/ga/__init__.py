"""Genetic Algorithm engine — pymoo NSGA-II + integrazione strategy registry.

Architettura:
    - ``chromosome.py``: encoding cromosoma per pymoo (mixed-type vars)
    - ``fitness.py``: fitness function multi-obiettivo su walk-forward
    - ``runner.py``: orchestrator con persistence DB + progress hooks
    - ``persistence.py``: helpers per save/load Population/Generation/Strategy
"""

from app.ga.chromosome import (
    ChromosomeSpec,
    build_chromosome_spec,
    decode_chromosome,
    encode_chromosome,
)
from app.ga.fitness import (
    FitnessConfig,
    FitnessResult,
    compute_fitness,
)

__all__ = [
    "ChromosomeSpec",
    "FitnessConfig",
    "FitnessResult",
    "build_chromosome_spec",
    "compute_fitness",
    "decode_chromosome",
    "encode_chromosome",
]
