from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd

from src.shared.config import Type1Config


def check_type1(
    symbol: str,
    earnings_data: list[dict],
    price_df: pd.DataFrame,
    institutional_ownership: dict,
    config: Type1Config,
    guidance_direction: Optional[str] = None,
    today: Optional[date] = None,
) -> tuple[bool, dict[str, bool]]:
    """TYPE-1 어닝 미반응 서프라이즈 조건 평가.

    Returns (all_conditions_met, conditions_dict).
    조건 모호 시 False (보수적 원칙).
    """
    today = today or date.today()
    conditions: dict[str, bool] = {}

    recent = _find_recent_earnings(earnings_data, today, config.scan_days_after_earnings)
    if recent is None:
        return False, {}

    eps_surprise = _calc_surprise(recent.get("actualEarningResult"), recent.get("estimatedEarning"))
    conditions["eps_surprise"] = eps_surprise is not None and eps_surprise > config.eps_surprise_min_pct

    rev_surprise = _calc_surprise(recent.get("actualRevenue"), recent.get("estimatedRevenue"))
    conditions["revenue_surprise"] = rev_surprise is not None and rev_surprise > config.revenue_surprise_min_pct

    direction = guidance_direction or "maintain"
    conditions["guidance_ok"] = direction != "down"

    earnings_date = pd.Timestamp(recent["date"])
    post_move = _calc_post_earnings_move(price_df, earnings_date)
    conditions["post_earnings_underreaction"] = (
        post_move is not None and post_move < config.post_earnings_move_max_pct
    )

    inst_pct = float(institutional_ownership.get("institutionalOwnershipPercentage", 0) or 0)
    conditions["institutional_ownership"] = inst_pct >= config.institutional_ownership_min

    all_met = len(conditions) == 5 and all(conditions.values())
    return all_met, conditions


def _find_recent_earnings(
    earnings_data: list[dict], today: date, scan_days: int
) -> dict | None:
    cutoff = today - timedelta(days=scan_days)
    for item in sorted(earnings_data, key=lambda x: x.get("date", ""), reverse=True):
        try:
            report_date = date.fromisoformat(item["date"])
        except (KeyError, ValueError):
            continue
        if cutoff <= report_date <= today:
            return item
    return None


def _calc_surprise(actual: object, estimated: object) -> float | None:
    try:
        a, e = float(actual), float(estimated)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if e == 0:
        return None
    return (a - e) / abs(e) * 100


def _calc_post_earnings_move(price_df: pd.DataFrame, earnings_date: pd.Timestamp) -> float | None:
    if price_df.empty:
        return None
    close_col = "close" if "close" in price_df.columns else "Close"
    if close_col not in price_df.columns:
        return None

    pre = price_df[price_df.index < earnings_date]
    post = price_df[price_df.index >= earnings_date]
    if pre.empty or post.empty:
        return None

    pre_close = float(pre[close_col].iloc[-1])
    post_close = float(post[close_col].iloc[0])
    if pre_close == 0:
        return None
    return (post_close - pre_close) / pre_close * 100
