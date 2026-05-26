from __future__ import annotations

import logging
import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_REGION = os.getenv("AWS_DEFAULT_REGION", "ap-northeast-2")


def upload_report(html_content: str, bucket: str, key: str,
                  expiry_days: int = 7) -> str:
    """HTML 리포트를 S3에 업로드하고 presigned URL을 반환."""
    client = boto3.client("s3", region_name=_REGION)

    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=html_content.encode("utf-8"),
            ContentType="text/html; charset=utf-8",
        )
        logger.info("S3 업로드 완료: s3://%s/%s", bucket, key)
    except ClientError as e:
        logger.error("S3 업로드 실패: %s", e)
        raise

    expiry_seconds = expiry_days * 86_400
    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expiry_seconds,
    )
    logger.info("Presigned URL 생성 완료 (유효기간 %d일)", expiry_days)
    return url


def make_report_key(symbol: str, signal_type: str, event_date: str) -> str:
    return f"reports/{signal_type.lower()}/{symbol}/{event_date}.html"
