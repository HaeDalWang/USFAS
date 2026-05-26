from __future__ import annotations

import json
import logging
from functools import lru_cache

import boto3

from src.shared.exceptions import SecretsError

logger = logging.getLogger(__name__)


@lru_cache(maxsize=None)
def _get_secret_raw(secret_arn: str, region: str = "ap-northeast-2") -> dict:
    client = boto3.client("secretsmanager", region_name=region)
    try:
        response = client.get_secret_value(SecretId=secret_arn)
    except Exception as e:
        raise SecretsError(f"Secrets Manager 조회 실패 ({secret_arn}): {e}") from e

    secret_string = response.get("SecretString")
    if not secret_string:
        raise SecretsError(f"SecretString 없음: {secret_arn}")

    try:
        return json.loads(secret_string)
    except json.JSONDecodeError:
        # 단순 문자열 시크릿인 경우
        return {"value": secret_string}


def get_fmp_api_key(arn: str) -> str:
    secret = _get_secret_raw(arn)
    key = secret.get("api_key") or secret.get("value")
    if not key:
        raise SecretsError(f"FMP API 키 필드 없음: {arn}")
    logger.info("FMP API 키 로드 완료")
    return key


def get_discord_webhook(arn: str) -> str:
    secret = _get_secret_raw(arn)
    url = secret.get("webhook_url") or secret.get("value")
    if not url:
        raise SecretsError(f"Discord Webhook URL 필드 없음: {arn}")
    logger.info("Discord Webhook 로드 완료")
    return url
