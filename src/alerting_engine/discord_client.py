from __future__ import annotations

import logging
import os

import requests

from src.shared.models import AlertSignal, KillSwitchStatus

logger = logging.getLogger(__name__)

_CONDITION_LABELS_TYPE1 = {
    "eps_surprise": "EPS 서프라이즈",
    "revenue_surprise": "매출 서프라이즈",
    "guidance_ok": "가이던스",
    "post_earnings_underreaction": "어닝 후 주가변동",
    "institutional_ownership": "기관 소유비율",
}

_CONDITION_LABELS_TYPE2 = {
    "min_executives": "C레벨 임원 수",
    "min_total_value": "총 매수금액",
    "price_drawdown": "52주 고점 대비 하락",
    "eps_profitable": "최근 분기 EPS",
}


def send_alert(webhook_url: str, signal: AlertSignal, report_url: str | None = None) -> None:
    content = _build_message(signal, report_url)
    payload = {"content": content}
    resp = requests.post(webhook_url, json=payload, timeout=10)
    resp.raise_for_status()
    logger.info("%s %s Discord 알림 발송 완료", signal.symbol, signal.signal_type)


def _build_message(signal: AlertSignal, report_url: str | None) -> str:
    parts: list[str] = []

    # Kill-Switch 경고 배너
    if signal.kill_switch_status.triggered:
        parts.append(_kill_switch_banner(signal.kill_switch_status))

    # 헤더
    if signal.signal_type == "TYPE1":
        parts.append("⚡ **[USFAS TYPE-1] 어닝 미반응 서프라이즈**")
    else:
        parts.append("🔍 **[USFAS TYPE-2] 내부자 클러스터 매수**")

    parts.append(f"\n📊 **{signal.symbol}** — {signal.company_name}")
    if signal.sector:
        parts.append(f"섹터: {signal.sector}")

    # 조건 체크
    parts.append("\n✅ **조건 체크**")
    labels = _CONDITION_LABELS_TYPE1 if signal.signal_type == "TYPE1" else _CONDITION_LABELS_TYPE2
    cond_lines = []
    items = list(signal.conditions_met.items())
    for i, (key, met) in enumerate(items):
        label = labels.get(key, key)
        icon = "✅" if met else "❌"
        prefix = "└" if i == len(items) - 1 else "├"
        cond_lines.append(f"{prefix} {label:<20} {icon}")
    parts.append("\n".join(cond_lines))

    # 손절 기준 (필수)
    parts.append(
        f"\n📉 **손절 기준**: -{_stop_pct(signal):.0f}% | ${signal.stop_loss_price:.2f}"
    )
    parts.append(f"💰 현재가: ${signal.current_price:.2f}")

    # VIX 상태
    ks = signal.kill_switch_status
    vix_icon = "🔴" if (ks.vix or 0) > 28 else "✅"
    parts.append(f"\n🌡️ VIX: {ks.vix:.1f} {vix_icon}" if ks.vix else "")

    # 리포트 링크
    if report_url:
        parts.append(f"📄 리포트: [링크]({report_url})")

    parts.append("\n⚠️ *투자 권유 아님 | 손절 필수*")

    return "\n".join(p for p in parts if p)


def _kill_switch_banner(ks: KillSwitchStatus) -> str:
    return (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ **Kill-Switch 작동 중! 매우 주의하세요**\n"
        f"사유: {ks.reason}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )


def _stop_pct(signal: AlertSignal) -> float:
    if signal.current_price == 0:
        return 0.0
    return (signal.current_price - signal.stop_loss_price) / signal.current_price * 100
