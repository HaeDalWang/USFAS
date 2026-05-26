from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd

from src.shared.config import Type2Config

_C_LEVEL_KEYWORDS = frozenset({
    "ceo", "cfo", "coo", "director", "chairman", "board",
    "chief executive", "chief financial", "chief operating",
})


def check_type2(
    symbol: str,
    insider_trades: list[dict],
    price_df: pd.DataFrame,
    income_statements: list[dict],
    config: Type2Config,
    today: Optional[date] = None,
) -> tuple[bool, dict[str, bool]]:
    """TYPE-2 내부자 클러스터 매수 조건 평가.

    Returns (all_conditions_met, conditions_dict).
    transaction_type == 'P' (공개시장 매수)만 카운트.
    """
    today = today or date.today()
    conditions: dict[str, bool] = {}

    cutoff = today - timedelta(days=config.lookback_days)
    public_buys = [
        t for t in insider_trades
        if t.get("transactionType") == "P"
        and _parse_date(t.get("filingDate")) >= cutoff
    ]

    c_level_buys = [t for t in public_buys if _is_c_level(t.get("officerTitle", ""))]
    unique_execs = len({t.get("officerTitle", "").lower() for t in c_level_buys})
    conditions["min_executives"] = unique_execs >= config.min_executives

    total_value = sum(
        float(t.get("securitiesTransacted", 0) or 0) * float(t.get("price", 0) or 0)
        for t in c_level_buys
    )
    conditions["min_total_value"] = total_value >= config.min_total_value_usd

    drawdown = _calc_52w_drawdown(price_df)
    conditions["price_drawdown"] = drawdown is not None and drawdown >= config.price_drawdown_min_pct

    if config.require_profitable:
        recent_eps = _get_recent_eps(income_statements)
        conditions["eps_profitable"] = recent_eps is not None and recent_eps > 0
    else:
        conditions["eps_profitable"] = True

    all_met = len(conditions) == 4 and all(conditions.values())
    return all_met, conditions


def _is_c_level(title: str) -> bool:
    t = title.lower()
    # "president"는 "vice president" 제외하고 C레벨로 인정
    if "president" in t and "vice" not in t:
        return True
    return any(kw in t for kw in _C_LEVEL_KEYWORDS)


def _parse_date(value: object) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return date.min


def _calc_52w_drawdown(price_df: pd.DataFrame) -> float | None:
    if price_df.empty:
        return None
    close_col = "close" if "close" in price_df.columns else "Close"
    if close_col not in price_df.columns:
        return None
    high_52w = float(price_df[close_col].max())
    current = float(price_df[close_col].iloc[-1])
    if high_52w == 0:
        return None
    return (high_52w - current) / high_52w * 100


def _get_recent_eps(income_statements: list[dict]) -> float | None:
    if not income_statements:
        return None
    try:
        return float(income_statements[0].get("eps") or 0)
    except (TypeError, ValueError):
        return None
