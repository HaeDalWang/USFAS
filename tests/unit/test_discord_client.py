from datetime import date
from unittest.mock import MagicMock, patch

import pytest
import responses as resp_mock

from src.alerting_engine.discord_client import _build_message, _kill_switch_banner, send_alert
from src.shared.models import AlertSignal, KillSwitchStatus


def _signal(signal_type: str = "TYPE1", kill_triggered: bool = False,
            kill_reason: str = "") -> AlertSignal:
    return AlertSignal(
        signal_type=signal_type,
        symbol="NVDA",
        company_name="NVIDIA Corporation",
        sector="Technology",
        market_cap=3_500_000_000_000,
        conditions_met={
            "eps_surprise": True,
            "revenue_surprise": True,
            "guidance_ok": True,
            "post_earnings_underreaction": True,
            "institutional_ownership": True,
        } if signal_type == "TYPE1" else {
            "min_executives": True,
            "min_total_value": True,
            "price_drawdown": True,
            "eps_profitable": True,
        },
        current_price=142.30,
        stop_loss_price=130.92,
        exit_date=None,
        kill_switch_status=KillSwitchStatus(
            triggered=kill_triggered,
            reason=kill_reason,
            vix=18.2,
        ),
    )


def test_type1_message_contains_required_fields():
    msg = _build_message(_signal("TYPE1"), report_url="https://s3.example.com/report")
    assert "TYPE-1" in msg
    assert "NVDA" in msg
    assert "130.92" in msg  # 손절 가격 필수
    assert "142.30" in msg  # 현재가
    assert "https://s3.example.com/report" in msg
    assert "투자 권유 아님" in msg


def test_type2_message_contains_required_fields():
    msg = _build_message(_signal("TYPE2"), report_url=None)
    assert "TYPE-2" in msg
    assert "NVDA" in msg
    assert "130.92" in msg


def test_kill_switch_banner_prepended_when_triggered():
    signal = _signal("TYPE1", kill_triggered=True, kill_reason="VIX 30.0 > 28.0")
    msg = _build_message(signal, report_url=None)
    # 경고 배너가 메시지 앞에 위치해야 함
    assert msg.index("Kill-Switch") < msg.index("TYPE-1")
    assert "VIX 30.0 > 28.0" in msg


def test_no_kill_switch_banner_when_not_triggered():
    msg = _build_message(_signal("TYPE1", kill_triggered=False), report_url=None)
    assert "Kill-Switch 작동 중" not in msg


def test_kill_switch_banner_format():
    ks = KillSwitchStatus(triggered=True, reason="VIX 29.4 > 28", vix=29.4)
    banner = _kill_switch_banner(ks)
    assert "Kill-Switch 작동 중" in banner
    assert "VIX 29.4 > 28" in banner


@resp_mock.activate
def test_send_alert_posts_to_webhook():
    resp_mock.add(resp_mock.POST, "https://discord.com/api/webhooks/test", status=204)
    send_alert("https://discord.com/api/webhooks/test", _signal("TYPE1"), "https://s3.url")
    assert len(resp_mock.calls) == 1
    assert "NVDA" in resp_mock.calls[0].request.body.decode("utf-8")


@resp_mock.activate
def test_send_alert_raises_on_http_error():
    resp_mock.add(resp_mock.POST, "https://discord.com/api/webhooks/test", status=400)
    with pytest.raises(Exception):
        send_alert("https://discord.com/api/webhooks/test", _signal("TYPE1"), None)
