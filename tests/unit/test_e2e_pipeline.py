"""
로컬 E2E 테스트 — AWS 서비스를 moto로 모킹하여 전체 파이프라인 검증.
실제 FMP API 호출 없이 responses 라이브러리로 HTTP 모킹.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from unittest.mock import patch

import boto3
import pandas as pd
import pytest
import responses as resp_mock
from moto import mock_aws

from src.data_collector.handler import run, _build_signal, _latest_filing_date
from src.shared.config import load_config, AppConfig
from src.shared.models import KillSwitchStatus

FMP_BASE = "https://financialmodelingprep.com/stable"
TODAY = date(2026, 5, 22)
EARNINGS_DATE = str(TODAY - timedelta(days=1))  # 어제 어닝 발표


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_caches():
    from src.shared.dynamo_client import _get_resource
    from src.shared.secrets import _get_secret_raw
    load_config.cache_clear()
    _get_resource.cache_clear()
    _get_secret_raw.cache_clear()
    yield
    load_config.cache_clear()
    _get_resource.cache_clear()
    _get_secret_raw.cache_clear()


@pytest.fixture
def config_file(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"""
universe:
  symbols: [NVDA]
providers:
  primary: fmp
  fallback: yfinance
kill_switch:
  vix_max: 28.0
  us10y_daily_bp_max: 15.0
  dxy_use_bollinger: true
  dxy_bollinger_period: 20
type1_earnings:
  eps_surprise_min_pct: 10.0
  revenue_surprise_min_pct: 3.0
  post_earnings_move_max_pct: 5.0
  institutional_ownership_min: 50.0
  scan_days_after_earnings: 2
type2_insider:
  min_executives: 2
  min_total_value_usd: 500000
  lookback_days: 30
  price_drawdown_min_pct: 25.0
  require_profitable: true
stop_loss:
  type1_pct: 8.0
  type1_exit_days_before_earnings: 2
  type2_pct: 12.0
  type2_max_hold_days: 90
report:
  s3_bucket: usfas-reports
  presigned_url_expiry_days: 7
secrets:
  fmp_api_key: arn:aws:secretsmanager:ap-northeast-2:123456789012:secret:usfas/fmp
  discord_webhook: arn:aws:secretsmanager:ap-northeast-2:123456789012:secret:usfas/discord
""")
    return str(cfg)


def _mock_price_df() -> pd.DataFrame:
    # TODAY로 끝나는 252 영업일 → EARNINGS_DATE(TODAY-1)가 범위 안에 포함됨
    dates = pd.date_range(end=pd.Timestamp(TODAY), periods=252, freq="B")
    closes = [200.0] * 100 + [130.0] * 152
    return pd.DataFrame({"close": closes}, index=dates)


def _mock_market_indicators():
    return {
        "vix": 18.0,
        "us10y_current": 4.35,
        "us10y_prev": 4.30,
        "dxy_series": pd.Series([99.0 if i % 2 == 0 else 101.0 for i in range(30)]),
    }


# ── E2E: TYPE-1 시그널 생성 ────────────────────────────────────────────────

@mock_aws
@resp_mock.activate
def test_e2e_type1_signal_generated(config_file):
    _setup_aws()

    # FMP API 모킹
    resp_mock.add(resp_mock.GET, f"{FMP_BASE}/earnings-surprises",
                  json=[{
                      "date": EARNINGS_DATE,
                      "symbol": "NVDA",
                      "actualEarningResult": 1.5,
                      "estimatedEarning": 1.2,
                      "actualRevenue": 100e9,
                      "estimatedRevenue": 95e9,
                  }], status=200)
    resp_mock.add(resp_mock.GET, f"{FMP_BASE}/institutional-ownership",
                  json=[{"institutionalOwnershipPercentage": 65.0}], status=200)
    resp_mock.add(resp_mock.GET, f"{FMP_BASE}/insider-trading",
                  json=[], status=200)
    resp_mock.add(resp_mock.GET, f"{FMP_BASE}/income-statement",
                  json=[{"eps": 2.5}], status=200)

    with patch("src.data_collector.handler.get_market_indicators", return_value=_mock_market_indicators()), \
         patch("src.data_collector.fmp_client.FMPClient.get_price_history", return_value=_mock_price_df()), \
         patch("src.shared.secrets.get_fmp_api_key", return_value="test-key"):
        signals = run(config_path=config_file, today=TODAY)

    assert len(signals) == 1
    assert signals[0].signal_type == "TYPE1"
    assert signals[0].symbol == "NVDA"
    assert signals[0].stop_loss_price < signals[0].current_price


@mock_aws
@resp_mock.activate
def test_e2e_idempotency_no_duplicate(config_file):
    """같은 어닝 이벤트로 두 번 실행해도 시그널은 1개만."""
    _setup_aws()

    for _ in range(2):
        resp_mock.add(resp_mock.GET, f"{FMP_BASE}/earnings-surprises",
                      json=[{"date": EARNINGS_DATE, "symbol": "NVDA",
                             "actualEarningResult": 1.5, "estimatedEarning": 1.2,
                             "actualRevenue": 100e9, "estimatedRevenue": 95e9}], status=200)
        resp_mock.add(resp_mock.GET, f"{FMP_BASE}/institutional-ownership",
                      json=[{"institutionalOwnershipPercentage": 65.0}], status=200)
        resp_mock.add(resp_mock.GET, f"{FMP_BASE}/insider-trading", json=[], status=200)
        resp_mock.add(resp_mock.GET, f"{FMP_BASE}/income-statement",
                      json=[{"eps": 2.5}], status=200)

    with patch("src.data_collector.handler.get_market_indicators", return_value=_mock_market_indicators()), \
         patch("src.data_collector.fmp_client.FMPClient.get_price_history", return_value=_mock_price_df()), \
         patch("src.shared.secrets.get_fmp_api_key", return_value="test-key"):
        signals_run1 = run(config_path=config_file, today=TODAY)
        signals_run2 = run(config_path=config_file, today=TODAY)

    assert len(signals_run1) == 1
    assert len(signals_run2) == 0  # 중복 방지


@mock_aws
@resp_mock.activate
def test_e2e_bulkhead_symbol_failure_continues(config_file, tmp_path):
    """한 종목 실패해도 나머지 계속 진행."""
    cfg = tmp_path / "config2.yaml"
    cfg.write_text(f"""
universe:
  symbols: [FAIL_SYMBOL, NVDA]
providers:
  primary: fmp
  fallback: yfinance
kill_switch:
  vix_max: 28.0
  us10y_daily_bp_max: 15.0
  dxy_use_bollinger: false
  dxy_bollinger_period: 20
type1_earnings:
  eps_surprise_min_pct: 10.0
  revenue_surprise_min_pct: 3.0
  post_earnings_move_max_pct: 5.0
  institutional_ownership_min: 50.0
  scan_days_after_earnings: 2
type2_insider:
  min_executives: 2
  min_total_value_usd: 500000
  lookback_days: 30
  price_drawdown_min_pct: 25.0
  require_profitable: true
stop_loss:
  type1_pct: 8.0
  type1_exit_days_before_earnings: 2
  type2_pct: 12.0
  type2_max_hold_days: 90
report:
  s3_bucket: usfas-reports
  presigned_url_expiry_days: 7
secrets:
  fmp_api_key: arn:aws:secretsmanager:ap-northeast-2:123456789012:secret:usfas/fmp
  discord_webhook: arn:aws:secretsmanager:ap-northeast-2:123456789012:secret:usfas/discord
""")
    _setup_aws()

    # NVDA만 정상 응답
    resp_mock.add(resp_mock.GET, f"{FMP_BASE}/earnings-surprises",
                  json=[{"date": EARNINGS_DATE, "symbol": "NVDA",
                         "actualEarningResult": 1.5, "estimatedEarning": 1.2,
                         "actualRevenue": 100e9, "estimatedRevenue": 95e9}], status=200)
    resp_mock.add(resp_mock.GET, f"{FMP_BASE}/institutional-ownership",
                  json=[{"institutionalOwnershipPercentage": 65.0}], status=200)
    resp_mock.add(resp_mock.GET, f"{FMP_BASE}/insider-trading", json=[], status=200)
    resp_mock.add(resp_mock.GET, f"{FMP_BASE}/income-statement",
                  json=[{"eps": 2.5}], status=200)

    def price_side_effect(symbol, days=365):
        if symbol == "FAIL_SYMBOL":
            raise Exception("네트워크 오류")
        return _mock_price_df()

    with patch("src.data_collector.handler.get_market_indicators", return_value=_mock_market_indicators()), \
         patch("src.data_collector.fmp_client.FMPClient.get_price_history", side_effect=price_side_effect), \
         patch("src.shared.secrets.get_fmp_api_key", return_value="test-key"):
        signals = run(config_path=str(cfg), today=TODAY)

    # FAIL_SYMBOL 스킵, NVDA 시그널 생성
    assert any(s.symbol == "NVDA" for s in signals)


# ── 유틸 ──────────────────────────────────────────────────────────────────

def test_latest_filing_date_empty():
    assert _latest_filing_date([]) == "unknown"


def test_latest_filing_date_picks_most_recent():
    trades = [
        {"filingDate": "2026-05-10"},
        {"filingDate": "2026-05-20"},
        {"filingDate": "2026-05-15"},
    ]
    assert _latest_filing_date(trades) == "2026-05-20"


def _setup_aws():
    """moto용 Secrets Manager + DynamoDB 초기화."""
    import os
    os.environ.setdefault("AWS_DEFAULT_REGION", "ap-northeast-2")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

    sm = boto3.client("secretsmanager", region_name="ap-northeast-2")
    sm.create_secret(
        Name="usfas/fmp",
        SecretString=json.dumps({"api_key": "test-fmp-key"}),
    )

    ddb = boto3.resource("dynamodb", region_name="ap-northeast-2")
    ddb.create_table(
        TableName="usfas-processed-events",
        AttributeDefinitions=[{"AttributeName": "event_id", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "event_id", "KeyType": "HASH"}],
        BillingMode="PAY_PER_REQUEST",
    )
