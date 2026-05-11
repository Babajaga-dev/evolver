"""System pipeline — feature flags, scheduler, maintenance.

Pipeline:
    settings.py     repository + default settings + tipi
    scheduler.py    AsyncIOScheduler integrato in FastAPI lifespan
    maintenance.py  cleanup DB (OHLCV, GA runs) + stats
"""

from app.system.settings import (
    DEFAULT_SETTINGS,
    SettingDefinition,
    get_setting,
    list_settings,
    set_setting_value,
)

__all__ = [
    "DEFAULT_SETTINGS",
    "SettingDefinition",
    "get_setting",
    "list_settings",
    "set_setting_value",
]
