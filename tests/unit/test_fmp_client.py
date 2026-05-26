import pytest
import responses as resp_mock
import pandas as pd
from unittest.mock import MagicMock, patch

from src.data_collector.fmp_client import FMPClient, get_market_indicators
from src.shared.exceptions import DataNotAvailable, FMPError, FMPFallbackError

API_KEY = "test-key"
BASE = "https://financialmodelingprep.com/stable"


@pytest.fixture
def client():
    return FMPClient(api_key=API_KEY)


# --- 초기화 ---

def test_empty_api_key_raises():
    with pytest.raises(ValueError, match="API 키"):
        FMPClient(api_key="")


# --- 재시도 로직 ---

@resp_mock.activate
def test_get_success_on_first_try(client):
    resp_mock.add(resp_mock.GET, f"{BASE}/earnings",
                  json=[{"symbol": "AAPL", "epsActual": 1.5, "epsEstimated": 1.2,
                         "revenueActual": 100e9, "revenueEstimated": 95e9, "date": "2026-05-01"}], status=200)
    data = client.get_earnings_surprises("AAPL")
    assert data[0]["symbol"] == "AAPL"


@resp_mock.activate
def test_get_retries_on_429_then_succeeds(client):
    resp_mock.add(resp_mock.GET, f"{BASE}/earnings", status=429)
    resp_mock.add(resp_mock.GET, f"{BASE}/earnings",
                  json=[{"symbol": "AAPL", "epsActual": 1.5, "epsEstimated": 1.2,
                         "revenueActual": 100e9, "revenueEstimated": 95e9, "date": "2026-05-01"}], status=200)
    with patch("time.sleep"):
        data = client.get_earnings_surprises("AAPL")
    assert data[0]["symbol"] == "AAPL"
    assert len(resp_mock.calls) == 2


@resp_mock.activate
def test_get_raises_fmp_error_after_max_retries(client):
    for _ in range(3):
        resp_mock.add(resp_mock.GET, f"{BASE}/earnings", status=500)
    with patch("time.sleep"):
        with pytest.raises(FMPError):
            client.get_earnings_surprises("AAPL")


# --- 어닝 서프라이즈 ---

@resp_mock.activate
def test_get_earnings_surprises_empty_raises(client):
    # 과거 실적 없음 (epsActual이 모두 null인 경우)
    resp_mock.add(resp_mock.GET, f"{BASE}/earnings",
                  json=[{"symbol": "AAPL", "epsActual": None, "epsEstimated": 1.2, "date": "2026-07-30"}],
                  status=200)
    with pytest.raises(DataNotAvailable, match="과거 어닝"):
        client.get_earnings_surprises("AAPL")


# --- 가격 데이터 + yfinance fallback ---

@resp_mock.activate
def test_get_price_history_fmp_success(client):
    resp_mock.add(resp_mock.GET, f"{BASE}/historical-price-eod/full", json={
        "historical": [
            {"date": "2026-05-01", "close": 180.0, "open": 178.0, "high": 182.0, "low": 177.0, "volume": 1000000},
            {"date": "2026-05-02", "close": 182.0, "open": 180.0, "high": 184.0, "low": 179.0, "volume": 1100000},
        ]
    }, status=200)
    df = client.get_price_history("AAPL", days=365)
    assert not df.empty
    assert "close" in df.columns


@resp_mock.activate
def test_get_price_history_falls_back_to_yfinance(client):
    resp_mock.add(resp_mock.GET, f"{BASE}/historical-price-eod/full", status=500)
    resp_mock.add(resp_mock.GET, f"{BASE}/historical-price-eod/full", status=500)
    resp_mock.add(resp_mock.GET, f"{BASE}/historical-price-eod/full", status=500)

    mock_df = pd.DataFrame({"Close": [180.0, 182.0]},
                           index=pd.to_datetime(["2026-05-01", "2026-05-02"]))
    with patch("time.sleep"), \
         patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = mock_df
        df = client.get_price_history("AAPL", days=365)

    assert not df.empty


@resp_mock.activate
def test_get_price_history_both_fail_raises(client):
    for _ in range(3):
        resp_mock.add(resp_mock.GET, f"{BASE}/historical-price-eod/full", status=500)

    with patch("time.sleep"), \
         patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = pd.DataFrame()
        with pytest.raises(FMPFallbackError):
            client.get_price_history("AAPL")


# --- 내부자 거래 ---

@resp_mock.activate
def test_get_insider_trading_returns_list(client):
    resp_mock.add(resp_mock.GET, f"{BASE}/insider-trading", json=[
        {"transactionType": "P", "officerTitle": "CEO", "securitiesTransacted": 1000, "price": 150.0},
        {"transactionType": "A", "officerTitle": "CFO", "securitiesTransacted": 500, "price": 150.0},
    ], status=200)
    data = client.get_insider_trading("META")
    assert len(data) == 2


# --- 시장 지표 (Kill-Switch용) ---

def test_get_market_indicators_returns_required_keys():
    mock_series_2 = pd.Series([18.0, 19.5], index=pd.to_datetime(["2026-05-25", "2026-05-26"]))
    mock_series_30 = pd.Series([104.0] * 30)

    with patch("yfinance.Ticker") as mock_ticker:
        def side_effect(symbol):
            m = MagicMock()
            if symbol == "^VIX":
                m.history.return_value = pd.DataFrame({"Close": mock_series_2})
            elif symbol == "^TNX":
                m.history.return_value = pd.DataFrame({"Close": mock_series_2})
            else:
                m.history.return_value = pd.DataFrame({"Close": mock_series_30})
            return m

        mock_ticker.side_effect = side_effect
        result = get_market_indicators()

    assert "vix" in result
    assert "us10y_current" in result
    assert "us10y_prev" in result
    assert "dxy_series" in result
    assert result["vix"] == pytest.approx(19.5)
