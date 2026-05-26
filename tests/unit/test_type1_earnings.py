from datetime import date

import pandas as pd
import pytest

from src.catalyst_detector.type1_earnings import check_type1, _calc_surprise, _find_recent_earnings
from src.shared.config import Type1Config


def _config() -> Type1Config:
    return Type1Config(
        eps_surprise_min_pct=10.0,
        revenue_surprise_min_pct=3.0,
        post_earnings_move_max_pct=5.0,
        institutional_ownership_min=50.0,
        scan_days_after_earnings=2,
    )


def _price_df(pre_close: float, post_close: float, earnings_date: str) -> pd.DataFrame:
    dates = pd.to_datetime([
        pd.Timestamp(earnings_date) - pd.Timedelta(days=1),
        pd.Timestamp(earnings_date),
    ])
    return pd.DataFrame({"close": [pre_close, post_close]}, index=dates)


def _earnings(date_str: str, actual_eps=1.5, est_eps=1.2,
               actual_rev=100e9, est_rev=95e9) -> list[dict]:
    return [{"date": date_str, "epsActual": actual_eps,
              "epsEstimated": est_eps, "revenueActual": actual_rev,
              "revenueEstimated": est_rev}]


def _inst(pct: float = 65.0) -> dict:
    return {"institutionalOwnershipPercentage": pct}


TODAY = date(2026, 5, 22)
EARNINGS_DATE = "2026-05-21"


def test_all_conditions_met():
    ok, conds = check_type1(
        "AAPL",
        _earnings(EARNINGS_DATE),
        _price_df(180.0, 182.0, EARNINGS_DATE),  # +1.1% 미반응
        _inst(65.0),
        _config(),
        guidance_direction="up",
        today=TODAY,
    )
    assert ok is True
    assert all(conds.values())
    assert len(conds) == 5


def test_eps_surprise_below_threshold():
    ok, conds = check_type1(
        "AAPL",
        _earnings(EARNINGS_DATE, actual_eps=1.25, est_eps=1.20),  # +4.2% < 10%
        _price_df(180.0, 182.0, EARNINGS_DATE),
        _inst(65.0),
        _config(),
        today=TODAY,
    )
    assert ok is False
    assert conds["eps_surprise"] is False


def test_revenue_surprise_below_threshold():
    ok, conds = check_type1(
        "AAPL",
        _earnings(EARNINGS_DATE, actual_rev=95e9, est_rev=95e9),  # 0% < 3%
        _price_df(180.0, 182.0, EARNINGS_DATE),
        _inst(65.0),
        _config(),
        today=TODAY,
    )
    assert ok is False
    assert conds["revenue_surprise"] is False


def test_guidance_down_fails():
    ok, conds = check_type1(
        "AAPL",
        _earnings(EARNINGS_DATE),
        _price_df(180.0, 182.0, EARNINGS_DATE),
        _inst(65.0),
        _config(),
        guidance_direction="down",
        today=TODAY,
    )
    assert ok is False
    assert conds["guidance_ok"] is False


def test_post_earnings_move_too_high():
    ok, conds = check_type1(
        "AAPL",
        _earnings(EARNINGS_DATE),
        _price_df(180.0, 200.0, EARNINGS_DATE),  # +11.1% 이미 반응
        _inst(65.0),
        _config(),
        today=TODAY,
    )
    assert ok is False
    assert conds["post_earnings_underreaction"] is False


def test_institutional_ownership_too_low():
    ok, conds = check_type1(
        "AAPL",
        _earnings(EARNINGS_DATE),
        _price_df(180.0, 182.0, EARNINGS_DATE),
        _inst(30.0),  # 30% < 50%
        _config(),
        today=TODAY,
    )
    assert ok is False
    assert conds["institutional_ownership"] is False


def test_earnings_too_old_returns_empty():
    old_date = "2026-05-10"  # 12일 전 — scan_days=2 초과
    ok, conds = check_type1(
        "AAPL",
        _earnings(old_date),
        _price_df(180.0, 182.0, old_date),
        _inst(65.0),
        _config(),
        today=TODAY,
    )
    assert ok is False
    assert conds == {}


def test_calc_surprise_zero_estimated_returns_none():
    assert _calc_surprise(1.5, 0) is None


def test_calc_surprise_none_values_returns_none():
    assert _calc_surprise(None, 1.2) is None
    assert _calc_surprise(1.5, None) is None


def test_calc_surprise_correct_value():
    result = _calc_surprise(1.5, 1.2)
    assert result == pytest.approx(25.0)
