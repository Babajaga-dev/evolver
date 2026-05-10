"""Schemi Pydantic per /api/v1/postmortem."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PostmortemRequest(BaseModel):
    days: int = 7


class PostmortemResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    markdown: str
    model: str
    tokens_input: int
    tokens_output: int
    cost_usd_estimate: float
