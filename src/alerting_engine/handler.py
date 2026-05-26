from __future__ import annotations

import logging
from datetime import date

from src.alerting_engine.discord_client import send_alert
from src.data_collector.fmp_client import FMPClient
from src.report_generator.chart_builder import build_type1_charts, build_type2_charts
from src.report_generator.html_renderer import render_type1_report, render_type2_report
from src.report_generator.s3_uploader import make_report_key, upload_report
from src.shared.config import AppConfig
from src.shared.models import AlertSignal

logger = logging.getLogger(__name__)


def process_signal(
    signal: AlertSignal,
    config: AppConfig,
    fmp_client: FMPClient,
    webhook_url: str,
) -> str | None:
    """시그널 처리: 차트 생성 → HTML 리포트 → S3 업로드 → Discord 알림."""
    try:
        price_df = fmp_client.get_price_history(signal.symbol, days=365)

        if signal.signal_type == "TYPE1":
            earnings = fmp_client.get_earnings_surprises(signal.symbol)
            inst = fmp_client.get_institutional_ownership(signal.symbol)
            charts = build_type1_charts(earnings, price_df, inst)
            html = render_type1_report(signal, charts, earnings)
        else:
            insider = fmp_client.get_insider_trading(signal.symbol)
            income = fmp_client.get_income_statement(signal.symbol)
            charts = build_type2_charts(insider, price_df, income)
            html = render_type2_report(signal, charts, insider)

        key = make_report_key(signal.symbol, signal.signal_type, str(date.today()))
        report_url = upload_report(
            html, config.report.s3_bucket, key, config.report.presigned_url_expiry_days
        )

        send_alert(webhook_url, signal, report_url)
        logger.info("%s %s 처리 완료: %s", signal.symbol, signal.signal_type, report_url)
        return report_url

    except Exception as e:
        logger.error("시그널 처리 실패 (%s %s): %s", signal.symbol, signal.signal_type, e,
                     exc_info=True)
        return None
