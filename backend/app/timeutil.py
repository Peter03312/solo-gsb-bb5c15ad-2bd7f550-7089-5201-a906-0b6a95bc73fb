"""时区与时间区间工具。

时间统一以 UTC 存储；输入允许形如 ``2026-10-04T09:00+08:00`` 或
``2026-10-04T09:00[Asia/Shanghai]``（后者仅用于提示）。
封闭区间为左闭右开 [start, end)。
"""
from datetime import datetime, timezone

from .errors import ApiError

# 常用 IANA 时区（前端下拉使用）
COMMON_TIMEZONES = [
    "Asia/Shanghai", "Asia/Tokyo", "Asia/Singapore", "Asia/Seoul",
    "Asia/Dubai", "Europe/London", "Europe/Berlin", "Europe/Moscow",
    "America/New_York", "America/Chicago", "America/Denver",
    "America/Los_Angeles", "Australia/Sydney", "Pacific/Auckland",
    "UTC",
]


def parse_dt(value: str, field: str = "时间") -> datetime:
    """解析带时区偏移的时间字符串，返回 UTC aware datetime。"""
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, "INVALID_TIME", f"{field}不能为空")
    text = value.strip()
    if "[" in text:
        text = text.split("[", 1)[0]
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        raise ApiError(
            400,
            "INVALID_TIME",
            f"{field}格式无效：{value!r}，应为 ISO 8601 带时区形式，如 2026-10-04T09:00+08:00",
        )
    if dt.tzinfo is None:
        raise ApiError(
            400,
            "INVALID_TIME",
            f"{field}必须带时区偏移，如 2026-10-04T09:00+08:00",
        )
    return dt.astimezone(timezone.utc)


def utc_str(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def union_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """左闭右开区间取并集；相接（a.end == b.start）也合并。"""
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged: list[list[float]] = [list(ordered[0])]
    for s, e in ordered[1:]:
        if s <= merged[-1][1]:
            if e > merged[-1][1]:
                merged[-1][1] = e
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]
