from __future__ import annotations

import base64
import io
import logging
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

logger = logging.getLogger(__name__)

_CHART_WIDTH = 700
_CHART_HEIGHT = 350
_TEMPLATE = "plotly_white"


def _to_base64(fig: go.Figure) -> str:
    try:
        png_bytes = fig.to_image(format="png", width=_CHART_WIDTH, height=_CHART_HEIGHT)
        return base64.b64encode(png_bytes).decode("utf-8")
    except Exception as e:
        logger.warning("차트 PNG 변환 실패 (kaleido 필요): %s", e)
        return ""


def build_type1_charts(
    earnings_data: list[dict],
    price_df: pd.DataFrame,
    institutional_data: dict,
    earnings_date: Optional[str] = None,
) -> dict[str, str]:
    return {
        "eps_history": _eps_surprise_history(earnings_data),
        "price_60d": _price_chart(price_df, days=60, marker_date=earnings_date, title="주가 (60일)"),
        "institutional": _institutional_chart(institutional_data),
    }


def build_type2_charts(
    insider_trades: list[dict],
    price_df: pd.DataFrame,
    income_statements: list[dict],
) -> dict[str, str]:
    return {
        "insider_timeline": _insider_timeline(insider_trades),
        "price_1y": _price_chart(price_df, days=252, marker_date=None, title="주가 (1년)"),
        "eps_quarterly": _eps_quarterly(income_statements),
    }


def _eps_surprise_history(earnings_data: list[dict]) -> str:
    recent = sorted(earnings_data, key=lambda x: x.get("date", ""), reverse=True)[:8]
    recent = list(reversed(recent))

    dates = [e.get("date", "")[:7] for e in recent]
    surprises = []
    for e in recent:
        actual = e.get("actualEarningResult")
        estimated = e.get("estimatedEarning")
        try:
            pct = (float(actual) - float(estimated)) / abs(float(estimated)) * 100
        except (TypeError, ValueError, ZeroDivisionError):
            pct = 0.0
        surprises.append(round(pct, 1))

    colors = ["#2ecc71" if s >= 0 else "#e74c3c" for s in surprises]
    fig = go.Figure(go.Bar(x=dates, y=surprises, marker_color=colors,
                           text=[f"{s:+.1f}%" for s in surprises], textposition="outside"))
    fig.update_layout(title="EPS 서프라이즈 히스토리 (8분기)", template=_TEMPLATE,
                      yaxis_title="서프라이즈 (%)", showlegend=False)
    return _to_base64(fig)


def _price_chart(price_df: pd.DataFrame, days: int, marker_date: Optional[str],
                 title: str) -> str:
    if price_df.empty:
        return ""
    close_col = "close" if "close" in price_df.columns else "Close"
    df = price_df.tail(days)
    fig = go.Figure(go.Scatter(x=df.index, y=df[close_col], mode="lines",
                               line=dict(color="#3498db", width=2)))
    if marker_date:
        fig.add_vline(x=marker_date, line_dash="dash", line_color="#e74c3c",
                      annotation_text="어닝 발표")
    fig.update_layout(title=title, template=_TEMPLATE, yaxis_title="종가 ($)")
    return _to_base64(fig)


def _institutional_chart(institutional_data: dict) -> str:
    pct = float(institutional_data.get("institutionalOwnershipPercentage", 0) or 0)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=pct,
        title={"text": "기관 소유비율 (%)"},
        gauge={"axis": {"range": [0, 100]},
               "bar": {"color": "#3498db"},
               "steps": [{"range": [0, 50], "color": "#fadbd8"},
                         {"range": [50, 100], "color": "#d5f5e3"}]},
    ))
    fig.update_layout(template=_TEMPLATE)
    return _to_base64(fig)


def _insider_timeline(insider_trades: list[dict]) -> str:
    buys = [t for t in insider_trades if t.get("transactionType") == "P"]
    if not buys:
        return ""
    dates = [t.get("filingDate", "")[:10] for t in buys]
    values = [float(t.get("securitiesTransacted", 0) or 0) *
              float(t.get("price", 0) or 0) / 1_000_000 for t in buys]
    titles = [t.get("officerTitle", "")[:20] for t in buys]

    fig = go.Figure(go.Bar(x=dates, y=values, text=titles, textposition="outside",
                           marker_color="#2ecc71"))
    fig.update_layout(title="내부자 공개시장 매수 타임라인", template=_TEMPLATE,
                      yaxis_title="매수금액 ($M)", showlegend=False)
    return _to_base64(fig)


def _eps_quarterly(income_statements: list[dict]) -> str:
    recent = sorted(income_statements, key=lambda x: x.get("date", ""), reverse=True)[:4]
    recent = list(reversed(recent))
    dates = [e.get("date", "")[:7] for e in recent]
    eps_vals = [float(e.get("eps", 0) or 0) for e in recent]
    colors = ["#2ecc71" if e >= 0 else "#e74c3c" for e in eps_vals]

    fig = go.Figure(go.Bar(x=dates, y=eps_vals, marker_color=colors,
                           text=[f"${e:.2f}" for e in eps_vals], textposition="outside"))
    fig.update_layout(title="최근 4분기 EPS", template=_TEMPLATE,
                      yaxis_title="EPS ($)", showlegend=False)
    return _to_base64(fig)
