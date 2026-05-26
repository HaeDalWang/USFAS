from __future__ import annotations

import logging
import os
from functools import lru_cache

import boto3
from boto3.dynamodb.conditions import Attr, Key

logger = logging.getLogger(__name__)

_REGION = os.getenv("AWS_DEFAULT_REGION", "ap-northeast-2")


@lru_cache(maxsize=None)
def _get_resource():
    return boto3.resource("dynamodb", region_name=_REGION)


def get_table(table_name: str):
    return _get_resource().Table(table_name)


class ProcessedEventsTable:
    """멱등성 관리 — 동일 이벤트 중복 알람 방지."""

    TABLE_NAME = "usfas-processed-events"

    def __init__(self):
        self._table = get_table(self.TABLE_NAME)

    def is_processed(self, symbol: str, event_type: str, event_date: str) -> bool:
        pk = f"{symbol}#{event_type}#{event_date}"
        response = self._table.get_item(Key={"event_id": pk})
        return "Item" in response

    def mark_processed(self, symbol: str, event_type: str, event_date: str) -> None:
        pk = f"{symbol}#{event_type}#{event_date}"
        self._table.put_item(Item={"event_id": pk})
        logger.info("이벤트 처리 완료 기록: %s", pk)
