import pytest

from src.report_generator.html_renderer import render_type1_report, render_type2_report
from src.shared.models import AlertSignal, KillSwitchStatus


def _signal(signal_type: str = "TYPE1", kill_triggered: bool = False) -> AlertSignal:
    return AlertSignal(
        signal_type=signal_type,
        symbol="NVDA",
        company_name="NVIDIA Corporation",
        sector="Technology",
        market_cap=0,
        conditions_met={"eps_surprise": True, "revenue_surprise": True,
                        "guidance_ok": True, "post_earnings_underreaction": True,
                        "institutional_ownership": True},
        current_price=142.30,
        stop_loss_price=130.92,
        exit_date=None,
        kill_switch_status=KillSwitchStatus(
            triggered=kill_triggered,
            reason="VIX 30.0 > 28.0" if kill_triggered else "",
            vix=30.0 if kill_triggered else 18.2,
        ),
    )


def test_type1_report_renders_symbol():
    html = render_type1_report(_signal("TYPE1"), charts={})
    assert "NVDA" in html
    assert "TYPE-1" in html


def test_type1_report_contains_stop_loss():
    html = render_type1_report(_signal("TYPE1"), charts={})
    assert "130.92" in html
    assert "142.30" in html


def test_type1_report_kill_switch_banner_shown():
    html = render_type1_report(_signal("TYPE1", kill_triggered=True), charts={})
    assert "Kill-Switch 작동 중" in html
    assert "VIX 30.0 > 28.0" in html


def test_type1_report_no_banner_when_not_triggered():
    html = render_type1_report(_signal("TYPE1", kill_triggered=False), charts={})
    assert "Kill-Switch 작동 중" not in html


def test_type2_report_renders_symbol():
    html = render_type2_report(_signal("TYPE2"), charts={})
    assert "NVDA" in html
    assert "TYPE-2" in html


def test_type1_report_embeds_chart_when_provided():
    charts = {"eps_history": "abc123base64=="}
    html = render_type1_report(_signal("TYPE1"), charts=charts)
    assert "abc123base64==" in html
    assert "data:image/png;base64," in html
