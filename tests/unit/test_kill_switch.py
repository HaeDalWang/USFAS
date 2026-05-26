import pandas as pd
import pytest

from src.catalyst_detector.kill_switch import check_kill_switch
from src.shared.config import KillSwitchConfig
from src.shared.models import KillSwitchStatus


def _config() -> KillSwitchConfig:
    return KillSwitchConfig(
        vix_max=28.0,
        us10y_daily_bp_max=15.0,
        dxy_use_bollinger=True,
        dxy_bollinger_period=20,
    )


def _dxy_series(current: float, period: int = 25) -> pd.Series:
    # 교대 값으로 분산 확보 → 볼린저 상단 ≈ 102, 100.5는 상단 아래
    base = [99.0 if i % 2 == 0 else 101.0 for i in range(period - 1)]
    return pd.Series(base + [current], dtype=float)


def test_not_triggered_normal_conditions():
    indicators = {
        "vix": 18.0,
        "us10y_current": 4.35,
        "us10y_prev": 4.30,
        "dxy_series": _dxy_series(100.5),
    }
    status = check_kill_switch(_config(), indicators)
    assert status.triggered is False
    assert status.reason == ""


def test_triggered_by_vix():
    indicators = {
        "vix": 30.0,
        "us10y_current": 4.35,
        "us10y_prev": 4.30,
        "dxy_series": _dxy_series(100.5),
    }
    status = check_kill_switch(_config(), indicators)
    assert status.triggered is True
    assert "VIX" in status.reason
    assert status.vix == pytest.approx(30.0)


def test_triggered_by_us10y():
    indicators = {
        "vix": 18.0,
        "us10y_current": 4.55,
        "us10y_prev": 4.35,  # +20bp
        "dxy_series": _dxy_series(100.5),
    }
    status = check_kill_switch(_config(), indicators)
    assert status.triggered is True
    assert "10Y" in status.reason
    assert status.us10y_change_bp == pytest.approx(20.0)


def test_triggered_by_dxy_bollinger():
    # 20개 값이 100.0이면 SMA=100, std≈0, upper≈100 → 110은 상단 돌파
    values = [100.0] * 20 + [110.0]
    dxy = pd.Series(values, dtype=float)
    indicators = {
        "vix": 18.0,
        "us10y_current": 4.35,
        "us10y_prev": 4.30,
        "dxy_series": dxy,
    }
    status = check_kill_switch(_config(), indicators)
    assert status.triggered is True
    assert "DXY" in status.reason
    assert status.dxy_above_bollinger is True


def test_multiple_triggers_combined_reason():
    indicators = {
        "vix": 35.0,
        "us10y_current": 4.60,
        "us10y_prev": 4.35,  # +25bp
        "dxy_series": _dxy_series(100.5),
    }
    status = check_kill_switch(_config(), indicators)
    assert status.triggered is True
    assert "VIX" in status.reason
    assert "10Y" in status.reason


def test_us10y_prev_none_skips_check():
    indicators = {
        "vix": 18.0,
        "us10y_current": 4.35,
        "us10y_prev": None,
        "dxy_series": _dxy_series(100.5),
    }
    status = check_kill_switch(_config(), indicators)
    assert status.triggered is False
    assert status.us10y_change_bp is None


def test_dxy_bollinger_disabled():
    cfg = KillSwitchConfig(
        vix_max=28.0,
        us10y_daily_bp_max=15.0,
        dxy_use_bollinger=False,
        dxy_bollinger_period=20,
    )
    values = [100.0] * 20 + [200.0]  # 극단적 DXY지만 볼린저 비활성화
    indicators = {
        "vix": 18.0,
        "us10y_current": 4.35,
        "us10y_prev": 4.30,
        "dxy_series": pd.Series(values, dtype=float),
    }
    status = check_kill_switch(cfg, indicators)
    assert status.triggered is False
