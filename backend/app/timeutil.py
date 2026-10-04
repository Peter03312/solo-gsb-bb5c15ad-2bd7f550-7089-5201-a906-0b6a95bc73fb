"""时间工具：所有时刻带时区输入，统一归一化为 UTC 存储与比较。

封闭区间为左闭右开 [start, end)。
"""
from __future__ import annotations

from datetime import datetime, timezone

from .errors import ApiError


def parse_tz(value: object, field: str) -> datetime:
    """解析带时区偏移的 ISO8601 字符串，返回带 tzinfo 的 datetime。"""
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, f"{field} 必填，需为带时区的 ISO8601 时间")
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        raise ApiError(400, f"{field} 时间格式无效：{value}")
    if dt.tzinfo is None:
        raise ApiError(400, f"{field} 必须带时区偏移（例如 2026-10-04T09:00+08:00）")
    return dt


def to_utc_iso(dt: datetime) -> str:
    """归一化为 UTC ISO8601 字符串（秒/微秒精度，Z 结尾）。"""
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_window(start: datetime, end: datetime):
    """校验封闭区间：起止都有效且 start < end（左闭右开要求严格小于）。"""
    if start >= end:
        raise ApiError(422, f"封闭区间无效：起始 {to_utc_iso(start)} 必须早于结束 {to_utc_iso(end)}")
