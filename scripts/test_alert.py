#!/usr/bin/env python3
"""Discord 테스트 알림 발송 스크립트 — FMP API 없이 직접 Discord 웹훅 검증."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.alerting_engine.discord_client import send_alert
from src.shared.models import AlertSignal, KillSwitchStatus

WEBHOOK_URL = "https://discord.com/api/webhooks/1508725076525056140/AeSjeLTeotNweIDCEIm3WiHZaAhdf3sW2eHfooG4UjJn6kjcT1Hl6kwaDEohCaIImuH2"


def _make_signal(signal_type: str, kill_triggered: bool = False) -> AlertSignal:
    conditions = (
        {"eps_surprise": True, "revenue_surprise": True, "guidance_ok": True,
         "post_earnings_underreaction": True, "institutional_ownership": True}
        if signal_type == "TYPE1"
        else {"min_executives": True, "min_total_value": True,
              "price_drawdown": True, "eps_profitable": True}
    )
    return AlertSignal(
        signal_type=signal_type,
        symbol="NVDA",
        company_name="NVIDIA Corporation",
        sector="Technology",
        market_cap=3_500_000_000_000,
        conditions_met=conditions,
        current_price=142.30,
        stop_loss_price=130.92 if signal_type == "TYPE1" else 125.22,
        exit_date=None,
        kill_switch_status=KillSwitchStatus(
            triggered=kill_triggered,
            reason="VIX 29.4 > 28.0" if kill_triggered else "",
            vix=29.4 if kill_triggered else 18.2,
            us10y_change_bp=5.0,
        ),
    )


if __name__ == "__main__":
    print("1️⃣  TYPE-1 정상 알림 발송...")
    send_alert(WEBHOOK_URL, _make_signal("TYPE1"), "https://example.com/report/type1")
    print("   ✅ 완료")

    print("2️⃣  TYPE-2 정상 알림 발송...")
    send_alert(WEBHOOK_URL, _make_signal("TYPE2"), "https://example.com/report/type2")
    print("   ✅ 완료")

    print("3️⃣  TYPE-1 + Kill-Switch 경고 배너 발송...")
    send_alert(WEBHOOK_URL, _make_signal("TYPE1", kill_triggered=True), None)
    print("   ✅ 완료")

    print("\n🎉 Discord 3개 알림 모두 발송 완료. Discord 채널 확인해봐!")
