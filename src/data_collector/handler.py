from __future__ import annotations

import logging
from datetime import date

from src.alerting_engine.handler import process_signal
from src.catalyst_detector.kill_switch import check_kill_switch
from src.catalyst_detector.type1_earnings import check_type1
from src.catalyst_detector.type2_insider import check_type2
from src.data_collector.fmp_client import FMPClient, get_market_indicators
from src.shared.config import AppConfig, load_config
from src.shared.dynamo_client import ProcessedEventsTable
from src.shared.exceptions import DataNotAvailable, FMPFallbackError
from src.shared.models import AlertSignal, KillSwitchStatus
from src.shared.secrets import get_discord_webhook, get_fmp_api_key

logger = logging.getLogger(__name__)


def run(config_path: str | None = None, today: date | None = None) -> list[AlertSignal]:
    config = load_config(config_path)
    api_key = get_fmp_api_key(config.secrets.fmp_api_key)
    webhook_url = get_discord_webhook(config.secrets.discord_webhook)
    fmp = FMPClient(api_key=api_key)
    events = ProcessedEventsTable()

    indicators = get_market_indicators()
    kill_status = check_kill_switch(config.kill_switch, indicators)

    if kill_status.triggered:
        logger.warning("⚠️ Kill-Switch 발동: %s", kill_status.reason)

    signals: list[AlertSignal] = []
    today = today or date.today()

    for symbol in config.universe.symbols:
        result = _scan_symbol(symbol, fmp, events, config, kill_status, today)
        signals.extend(result)

    logger.info("스캔 완료: %d개 종목, %d개 시그널", len(config.universe.symbols), len(signals))

    for signal in signals:
        process_signal(signal, config, fmp, webhook_url)

    return signals


def _scan_symbol(
    symbol: str,
    fmp: FMPClient,
    events: ProcessedEventsTable,
    config: AppConfig,
    kill_status: KillSwitchStatus,
    today: date,
) -> list[AlertSignal]:
    try:
        return _do_scan(symbol, fmp, events, config, kill_status, today)
    except (DataNotAvailable, FMPFallbackError) as e:
        logger.warning("%s: 데이터 없음, 스킵 — %s", symbol, e)
        return []
    except Exception as e:
        logger.error("%s: 오류 발생, 스킵 — %s", symbol, e, exc_info=True)
        return []


def _do_scan(
    symbol: str,
    fmp: FMPClient,
    events: ProcessedEventsTable,
    config: AppConfig,
    kill_status: KillSwitchStatus,
    today: date,
) -> list[AlertSignal]:
    signals: list[AlertSignal] = []
    price_df = fmp.get_price_history(symbol, days=365)

    # TYPE-1
    try:
        earnings = fmp.get_earnings_surprises(symbol)
        inst = fmp.get_institutional_ownership(symbol)
        t1_ok, t1_conds = check_type1(
            symbol, earnings, price_df, inst, config.type1_earnings, today=today
        )
        if t1_ok:
            event_date = earnings[0]["date"]
            if not events.is_processed(symbol, "TYPE1", event_date):
                signal = _build_signal("TYPE1", symbol, t1_conds, price_df, config, kill_status)
                signals.append(signal)
                events.mark_processed(symbol, "TYPE1", event_date)
                logger.info("%s TYPE-1 시그널 생성", symbol)
    except DataNotAvailable:
        logger.debug("%s: TYPE-1 데이터 없음", symbol)

    # TYPE-2
    try:
        insider = fmp.get_insider_trading(symbol)
        income = fmp.get_income_statement(symbol)
        t2_ok, t2_conds = check_type2(
            symbol, insider, price_df, income, config.type2_insider, today=today
        )
        if t2_ok:
            event_key = _latest_filing_date(insider)
            if not events.is_processed(symbol, "TYPE2", event_key):
                signal = _build_signal("TYPE2", symbol, t2_conds, price_df, config, kill_status)
                signals.append(signal)
                events.mark_processed(symbol, "TYPE2", event_key)
                logger.info("%s TYPE-2 시그널 생성", symbol)
    except DataNotAvailable:
        logger.debug("%s: TYPE-2 데이터 없음", symbol)

    return signals


def _build_signal(
    signal_type: str,
    symbol: str,
    conditions: dict[str, bool],
    price_df,
    config: AppConfig,
    kill_status: KillSwitchStatus,
) -> AlertSignal:
    import pandas as pd

    close_col = "close" if "close" in price_df.columns else "Close"
    current_price = float(price_df[close_col].iloc[-1])

    sl_cfg = config.stop_loss
    stop_pct = sl_cfg.type1_pct if signal_type == "TYPE1" else sl_cfg.type2_pct
    stop_loss_price = round(current_price * (1 - stop_pct / 100), 2)

    return AlertSignal(
        signal_type=signal_type,
        symbol=symbol,
        company_name=symbol,
        sector="",
        market_cap=0.0,
        conditions_met=conditions,
        current_price=current_price,
        stop_loss_price=stop_loss_price,
        exit_date=None,
        kill_switch_status=kill_status,
    )


def _latest_filing_date(insider_trades: list[dict]) -> str:
    if not insider_trades:
        return "unknown"
    latest = max(insider_trades, key=lambda t: t.get("filingDate", ""))
    return str(latest.get("filingDate", "unknown"))[:10]
