from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.shared.models import AlertSignal

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )


def render_type1_report(signal: AlertSignal, charts: dict[str, str],
                        earnings_data: list[dict] | None = None) -> str:
    template = _env().get_template("type1_report.html.j2")
    return template.render(signal=signal, charts=charts,
                           earnings_data=earnings_data or [])


def render_type2_report(signal: AlertSignal, charts: dict[str, str],
                        insider_trades: list[dict] | None = None) -> str:
    template = _env().get_template("type2_report.html.j2")
    return template.render(signal=signal, charts=charts,
                           insider_trades=insider_trades or [])
