from __future__ import annotations

import pandas as pd

from src.shared.config import KillSwitchConfig
from src.shared.models import KillSwitchStatus


def check_kill_switch(config: KillSwitchConfig, indicators: dict) -> KillSwitchStatus:
    """VIX / US 10Y / DXY 조건 평가. 스캔은 계속 진행, 알림에 경고 배너 추가용."""
    reasons: list[str] = []
    us10y_change_bp: float | None = None
    dxy_above = False

    vix = indicators["vix"]
    if vix > config.vix_max:
        reasons.append(f"VIX {vix:.1f} > {config.vix_max}")

    us10y_current = indicators.get("us10y_current")
    us10y_prev = indicators.get("us10y_prev")
    if us10y_current is not None and us10y_prev is not None:
        us10y_change_bp = (us10y_current - us10y_prev) * 100
        if us10y_change_bp > config.us10y_daily_bp_max:
            reasons.append(f"US 10Y +{us10y_change_bp:.1f}bp > {config.us10y_daily_bp_max}bp")

    if config.dxy_use_bollinger:
        dxy_series: pd.Series | None = indicators.get("dxy_series")
        if dxy_series is not None and len(dxy_series) >= config.dxy_bollinger_period:
            rolling = dxy_series.rolling(config.dxy_bollinger_period)
            upper = rolling.mean().iloc[-1] + 2 * rolling.std().iloc[-1]
            current_dxy = float(dxy_series.iloc[-1])
            if current_dxy > upper:
                dxy_above = True
                reasons.append(f"DXY {current_dxy:.2f} > 볼린저 상단 {upper:.2f}")

    return KillSwitchStatus(
        triggered=len(reasons) > 0,
        reason=" | ".join(reasons),
        vix=vix,
        us10y_change_bp=us10y_change_bp,
        dxy_above_bollinger=dxy_above,
    )
