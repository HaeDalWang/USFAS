from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from src.shared.exceptions import ConfigError

_DEFAULT_CONFIG_PATH = Path(__file__).parents[2] / "config.yaml"


class UniverseConfig(BaseModel):
    symbols: list[str]


class ProvidersConfig(BaseModel):
    primary: str = "fmp"
    fallback: str = "yfinance"


class KillSwitchConfig(BaseModel):
    vix_max: float = Field(gt=0)
    us10y_daily_bp_max: float = Field(gt=0)
    dxy_use_bollinger: bool = True
    dxy_bollinger_period: int = Field(ge=5, le=200)


class Type1Config(BaseModel):
    eps_surprise_min_pct: float = Field(gt=0, le=100)
    revenue_surprise_min_pct: float = Field(gt=0, le=100)
    post_earnings_move_max_pct: float = Field(gt=0, le=50)
    institutional_ownership_min: float = Field(ge=0, le=100)
    scan_days_after_earnings: int = Field(ge=1, le=5)


class Type2Config(BaseModel):
    min_executives: int = Field(ge=1)
    min_total_value_usd: int = Field(gt=0)
    lookback_days: int = Field(ge=1, le=90)
    price_drawdown_min_pct: float = Field(gt=0, le=100)
    require_profitable: bool = True


class StopLossConfig(BaseModel):
    type1_pct: float = Field(gt=0, le=50)
    type1_exit_days_before_earnings: int = Field(ge=0, le=10)
    type2_pct: float = Field(gt=0, le=50)
    type2_max_hold_days: int = Field(ge=1, le=365)


class ReportConfig(BaseModel):
    s3_bucket: str
    presigned_url_expiry_days: int = Field(ge=1, le=7)


class SecretsConfig(BaseModel):
    fmp_api_key: str
    discord_webhook: str


class AppConfig(BaseModel):
    universe: UniverseConfig
    providers: ProvidersConfig
    kill_switch: KillSwitchConfig
    type1_earnings: Type1Config
    type2_insider: Type2Config
    stop_loss: StopLossConfig
    report: ReportConfig
    secrets: SecretsConfig


@lru_cache(maxsize=1)
def load_config(path: str | None = None) -> AppConfig:
    config_path = Path(path) if path else Path(os.getenv("USFAS_CONFIG", str(_DEFAULT_CONFIG_PATH)))
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ConfigError(f"config.yaml 없음: {config_path}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"config.yaml 파싱 실패: {e}") from e

    try:
        return AppConfig.model_validate(raw)
    except Exception as e:
        raise ConfigError(f"config.yaml 검증 실패: {e}") from e
