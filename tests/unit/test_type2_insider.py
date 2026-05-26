from datetime import date

import pandas as pd
import pytest

from src.catalyst_detector.type2_insider import check_type2, _is_c_level
from src.shared.config import Type2Config


def _config() -> Type2Config:
    return Type2Config(
        min_executives=2,
        min_total_value_usd=500_000,
        lookback_days=30,
        price_drawdown_min_pct=25.0,
        require_profitable=True,
    )


def _price_df(high: float = 200.0, current: float = 130.0) -> pd.DataFrame:
    dates = pd.date_range("2025-05-22", periods=252, freq="B")
    closes = [high] * 100 + [current] * 152
    return pd.DataFrame({"close": closes}, index=dates)


def _trade(title: str, value: float = 300_000, date_str: str = "2026-05-10",
           tx_type: str = "P") -> dict:
    return {
        "filingDate": date_str,
        "transactionType": tx_type,
        "securitiesTransacted": value / 100,
        "price": 100.0,
        "officerTitle": title,
    }


def _income(eps: float = 2.5) -> list[dict]:
    return [{"date": "2026-03-31", "eps": eps}]


TODAY = date(2026, 5, 22)


def test_all_conditions_met():
    trades = [_trade("CEO"), _trade("CFO")]
    ok, conds = check_type2("META", trades, _price_df(), _income(), _config(), today=TODAY)
    assert ok is True
    assert all(conds.values())


def test_option_exercises_excluded():
    trades = [_trade("CEO", tx_type="A"), _trade("CFO", tx_type="A")]
    ok, conds = check_type2("META", trades, _price_df(), _income(), _config(), today=TODAY)
    assert ok is False
    assert conds["min_executives"] is False


def test_not_enough_c_level_executives():
    trades = [_trade("CEO")]  # 1명만
    ok, conds = check_type2("META", trades, _price_df(), _income(), _config(), today=TODAY)
    assert ok is False
    assert conds["min_executives"] is False


def test_total_value_too_low():
    trades = [_trade("CEO", value=100_000), _trade("CFO", value=100_000)]
    ok, conds = check_type2("META", trades, _price_df(), _income(), _config(), today=TODAY)
    assert ok is False
    assert conds["min_total_value"] is False


def test_price_not_in_drawdown():
    # 고점 200, 현재 190 → 5% 하락 < 25%
    ok, conds = check_type2(
        "META",
        [_trade("CEO"), _trade("CFO")],
        _price_df(high=200.0, current=190.0),
        _income(),
        _config(),
        today=TODAY,
    )
    assert ok is False
    assert conds["price_drawdown"] is False


def test_eps_negative_fails():
    ok, conds = check_type2(
        "META",
        [_trade("CEO"), _trade("CFO")],
        _price_df(),
        _income(eps=-0.5),
        _config(),
        today=TODAY,
    )
    assert ok is False
    assert conds["eps_profitable"] is False


def test_trades_outside_lookback_excluded():
    old_trade = _trade("CEO", date_str="2026-03-01")  # 82일 전
    recent_trade = _trade("CFO", date_str="2026-05-10")
    ok, conds = check_type2(
        "META",
        [old_trade, recent_trade],
        _price_df(),
        _income(),
        _config(),
        today=TODAY,
    )
    assert ok is False
    assert conds["min_executives"] is False  # CEO 제외되어 1명만


def test_is_c_level_detection():
    assert _is_c_level("Chief Executive Officer") is True
    assert _is_c_level("CEO") is True
    assert _is_c_level("Chief Financial Officer") is True
    assert _is_c_level("Board of Directors") is True
    assert _is_c_level("Senior Vice President") is False
    assert _is_c_level("Director of Engineering") is True


def test_require_profitable_false_skips_eps_check():
    cfg = Type2Config(
        min_executives=2,
        min_total_value_usd=500_000,
        lookback_days=30,
        price_drawdown_min_pct=25.0,
        require_profitable=False,
    )
    ok, conds = check_type2(
        "META",
        [_trade("CEO"), _trade("CFO")],
        _price_df(),
        _income(eps=-5.0),
        cfg,
        today=TODAY,
    )
    assert conds["eps_profitable"] is True
