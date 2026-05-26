from __future__ import annotations

import logging
from dataclasses import dataclass

from src.catalyst_detector.kill_switch import check_kill_switch
from src.catalyst_detector.type1_earnings import check_type1
from src.catalyst_detector.type2_insider import check_type2
from src.data_collector.fmp_client import FMPClient, get_market_indicators
from src.shared.config import AppConfig
from src.shared.dynamo_client import ProcessedEventsTable
from src.shared.exceptions import DataNotAvailable, FMPFallbackError
from src.shared.models import AlertSignal, KillSwitchStatus

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    symbol: str
    signals: list[AlertSignal]
    skipped: bool = False
    skip_reason: str = ""


class CatalystDetector:
    def __init__(self, config: AppConfig, fmp_client: FMPClient):
        self._config = config
        self._fmp = fmp_client
        self._events = ProcessedEventsTable()

    def run(self) -> list[AlertSignal]:
        indicators = get_market_indicators()
        kill_status = check_kill_switch(self._config.kill_switch, indicators)

        if kill_status.triggered:
            logger.warning("Kill-Switch 발동: %s", kill_status.reason)

        signals: list[AlertSignal] = []
        for symbol in self._config.universe.symbols:
            result = self._scan_symbol(symbol, kill_status)
            if not result.skipped:
                signals.extend(result.signals)

        return signals

    def _scan_symbol(self, symbol: str, kill_status: KillSwitchStatus) -> ScanResult:
        try:
            return self._do_scan(symbol, kill_status)
        except (DataNotAvailable, FMPFallbackError) as e:
            logger.warning("%s: 데이터 없음, 스킵 — %s", symbol, e)
            return ScanResult(symbol=symbol, signals=[], skipped=True, skip_reason=str(e))
        except Exception as e:
            logger.error("%s: 예상치 못한 오류, 스킵 — %s", symbol, e, exc_info=True)
            return ScanResult(symbol=symbol, signals=[], skipped=True, skip_reason=str(e))

    def _do_scan(self, symbol: str, kill_status: KillSwitchStatus) -> ScanResult:
        signals: list[AlertSignal] = []

        price_df = self._fmp.get_price_history(symbol, days=365)

        # TYPE-1 체크
        try:
            earnings = self._fmp.get_earnings_surprises(symbol)
            inst = self._fmp.get_institutional_ownership(symbol)
            t1_ok, t1_conds = check_type1(
                symbol, earnings, price_df, inst, self._config.type1_earnings
            )
            if t1_ok and not self._is_processed(symbol, "TYPE1", earnings[0]["date"]):
                signals.append(self._build_signal("TYPE1", symbol, t1_conds, price_df, kill_status))
                self._events.mark_processed(symbol, "TYPE1", earnings[0]["date"])
        except DataNotAvailable:
            logger.debug("%s: TYPE-1 데이터 없음", symbol)

        # TYPE-2 체크
        try:
            insider = self._fmp.get_insider_trading(symbol)
            income = self._fmp.get_income_statement(symbol)
            t2_ok, t2_conds = check_type2(
                symbol, insider, price_df, income, self._config.type2_insider
            )
            if t2_ok:
                event_key = _insider_event_key(insider)
                if not self._is_processed(symbol, "TYPE2", event_key):
                    signals.append(self._build_signal("TYPE2", symbol, t2_conds, price_df, kill_status))
                    self._events.mark_processed(symbol, "TYPE2", event_key)
        except DataNotAvailable:
            logger.debug("%s: TYPE-2 데이터 없음", symbol)

        return ScanResult(symbol=symbol, signals=signals)

    def _is_processed(self, symbol: str, event_type: str, event_date: str) -> bool:
        return self._events.is_processed(symbol, event_type, event_date)

    def _build_signal(
        self,
        signal_type: str,
        symbol: str,
        conditions: dict[str, bool],
        price_df: pd.DataFrame,
        kill_status: KillSwitchStatus,
    ) -> AlertSignal:
        import pandas as pd

        close_col = "close" if "close" in price_df.columns else "Close"
        current_price = float(price_df[close_col].iloc[-1])

        cfg = self._config.stop_loss
        if signal_type == "TYPE1":
            stop_loss = current_price * (1 - cfg.type1_pct / 100)
        else:
            stop_loss = current_price * (1 - cfg.type2_pct / 100)

        return AlertSignal(
            signal_type=signal_type,
            symbol=symbol,
            company_name=symbol,
            sector="",
            market_cap=0.0,
            conditions_met=conditions,
            current_price=current_price,
            stop_loss_price=round(stop_loss, 2),
            exit_date=None,
            kill_switch_status=kill_status,
        )


def _insider_event_key(insider_trades: list[dict]) -> str:
    if not insider_trades:
        return "unknown"
    latest = max(insider_trades, key=lambda t: t.get("filingDate", ""))
    return latest.get("filingDate", "unknown")[:10]
