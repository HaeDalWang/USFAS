from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import requests
import yfinance as yf

from src.shared.exceptions import DataNotAvailable, FMPError, FMPFallbackError

logger = logging.getLogger(__name__)

_BASE_URL = "https://financialmodelingprep.com/stable"
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0


class FMPClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("FMP API 키가 비어 있음")
        self._api_key = api_key
        self._session = requests.Session()

    def _get(self, endpoint: str, params: dict | None = None) -> list | dict:
        url = f"{_BASE_URL}/{endpoint}"
        all_params = {"apikey": self._api_key, **(params or {})}

        delay = _RETRY_BASE_DELAY
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._session.get(url, params=all_params, timeout=30)
                if resp.status_code == 429:
                    logger.warning("FMP 429 rate limit, %.1fs 대기 (시도 %d/%d)", delay, attempt + 1, _MAX_RETRIES)
                    time.sleep(delay)
                    delay *= 2
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                last_error = e
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(delay)
                    delay *= 2

        raise FMPError(f"FMP API 실패 ({endpoint}): {last_error}")

    def get_earnings_surprises(self, symbol: str) -> list[dict]:
        # stable API는 'earnings' 엔드포인트 사용 ('earnings-surprises'는 404)
        data = self._get("earnings", {"symbol": symbol})
        # 과거 실적만 (epsActual이 있는 것)
        past = [e for e in data if e.get("epsActual") is not None]
        if not past:
            raise DataNotAvailable(f"{symbol}: 과거 어닝 데이터 없음")
        return past

    def get_price_history(self, symbol: str, days: int = 365) -> pd.DataFrame:
        try:
            return self._get_price_fmp(symbol, days)
        except FMPError:
            logger.warning("%s: FMP 가격 데이터 실패, yfinance fallback", symbol)
            return self._get_price_yfinance(symbol, days)

    def _get_price_fmp(self, symbol: str, days: int) -> pd.DataFrame:
        data = self._get("historical-price-eod/full", {"symbol": symbol})
        if not data or "historical" not in data:
            raise FMPError(f"{symbol}: FMP 가격 데이터 비어 있음")
        df = pd.DataFrame(data["historical"])
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").set_index("date")
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        return df[df.index >= pd.Timestamp(cutoff)]

    def _get_price_yfinance(self, symbol: str, days: int) -> pd.DataFrame:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=f"{days}d")
        if df.empty:
            raise FMPFallbackError(f"{symbol}: yfinance 가격 데이터도 없음")
        return df

    def get_institutional_ownership(self, symbol: str) -> dict:
        try:
            data = self._get("institutional-ownership", {"symbol": symbol})
            if data:
                return data[0] if isinstance(data, list) else data
        except (FMPError, Exception):
            pass
        # yfinance fallback (FMP Starter 플랜 없을 때)
        logger.warning("%s: FMP 기관 소유비율 없음, yfinance fallback", symbol)
        return self._get_institutional_yfinance(symbol)

    def _get_institutional_yfinance(self, symbol: str) -> dict:
        ticker = yf.Ticker(symbol)
        pct = (ticker.info.get("heldPercentInstitutions") or 0) * 100
        return {"institutionalOwnershipPercentage": round(pct, 2)}

    def get_insider_trading(self, symbol: str) -> list[dict]:
        try:
            data = self._get("insider-trading", {"symbol": symbol})
            if not isinstance(data, list):
                raise DataNotAvailable(f"{symbol}: 내부자 거래 데이터 없음")
            return data
        except FMPError as e:
            # FMP Starter 플랜 필요 — 빈 리스트 반환 (TYPE-2 조건 미충족으로 처리)
            logger.warning("%s: insider-trading 접근 불가 (FMP Starter 플랜 필요): %s", symbol, e)
            return []

    def get_income_statement(self, symbol: str, period: str = "quarter") -> list[dict]:
        data = self._get("income-statement", {"symbol": symbol, "period": period})
        if not data:
            raise DataNotAvailable(f"{symbol}: 손익계산서 데이터 없음")
        return data


def get_market_indicators() -> dict:
    """VIX, US 10Y, DXY 현재값 조회 (Kill-Switch용, yfinance 전용)."""
    try:
        vix_hist = yf.Ticker("^VIX").history(period="2d")["Close"]
        us10y_hist = yf.Ticker("^TNX").history(period="2d")["Close"]
        dxy_hist = yf.Ticker("DX-Y.NYB").history(period="30d")["Close"]

        return {
            "vix": float(vix_hist.iloc[-1]),
            "us10y_current": float(us10y_hist.iloc[-1]),
            "us10y_prev": float(us10y_hist.iloc[-2]) if len(us10y_hist) >= 2 else None,
            "dxy_series": dxy_hist,
        }
    except Exception as e:
        raise FMPError(f"시장 지표 조회 실패: {e}") from e
