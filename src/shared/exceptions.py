class FMPError(Exception):
    """FMP API 호출 실패 (재시도 소진 포함)."""


class FMPFallbackError(Exception):
    """FMP + yfinance 양쪽 모두 실패."""


class DataNotAvailable(Exception):
    """필요한 데이터가 존재하지 않음 (종목 스킵 대상)."""


class ConfigError(Exception):
    """config.yaml 로드 또는 검증 실패."""


class SecretsError(Exception):
    """AWS Secrets Manager 조회 실패."""
