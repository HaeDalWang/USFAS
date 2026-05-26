import pytest
from pathlib import Path
from unittest.mock import patch

from src.shared.config import load_config, AppConfig
from src.shared.exceptions import ConfigError


@pytest.fixture(autouse=True)
def clear_cache():
    load_config.cache_clear()
    yield
    load_config.cache_clear()


def test_load_config_success(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("""
universe:
  symbols: [AAPL, MSFT]
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
  fmp_api_key: arn:aws:secretsmanager:ap-northeast-2:123:secret:usfas/fmp
  discord_webhook: arn:aws:secretsmanager:ap-northeast-2:123:secret:usfas/discord
""")
    config = load_config(str(cfg_file))
    assert isinstance(config, AppConfig)
    assert config.universe.symbols == ["AAPL", "MSFT"]
    assert config.kill_switch.vix_max == 28.0
    assert config.type1_earnings.scan_days_after_earnings == 2
    assert config.type2_insider.min_executives == 2


def test_load_config_missing_file():
    with pytest.raises(ConfigError, match="config.yaml 없음"):
        load_config("/nonexistent/path/config.yaml")


def test_load_config_invalid_yaml(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("invalid: yaml: [\nbroken")
    with pytest.raises(ConfigError, match="파싱 실패"):
        load_config(str(cfg_file))


def test_load_config_validation_error(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("""
universe:
  symbols: [AAPL]
providers:
  primary: fmp
  fallback: yfinance
kill_switch:
  vix_max: -1.0
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
  fmp_api_key: arn:test
  discord_webhook: arn:test
""")
    with pytest.raises(ConfigError, match="검증 실패"):
        load_config(str(cfg_file))


def test_symbols_list_not_empty(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("""
universe:
  symbols: [NVDA, META, GOOGL]
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
  fmp_api_key: arn:test
  discord_webhook: arn:test
""")
    config = load_config(str(cfg_file))
    assert len(config.universe.symbols) == 3
