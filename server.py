#!/usr/bin/env python3
import json
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP

BASE_URL = "https://services.surfline.com/kbyg/spots/forecasts"
DEFAULT_DAYS = 3
REQUEST_TIMEOUT_SECONDS = 20

mcp = FastMCP("surfline-mcp")


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _fetch_forecast(endpoint: str, spot_id: str, days: int) -> dict[str, Any]:
    query = urlencode({"spotId": spot_id, "days": str(days)})
    url = f"{BASE_URL}/{endpoint}?{query}"

    req = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "surfline-mcp/1.0",
        },
        method="GET",
    )

    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            payload = resp.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Surfline HTTP {exc.code} from endpoint '{endpoint}': {detail[:300]}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"Surfline request failed for endpoint '{endpoint}': {exc}") from exc

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON returned by endpoint '{endpoint}': {exc}"
        ) from exc


def _simplify_conditions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("data", {}).get("conditions", [])
    if not isinstance(items, list):
        return []

    simplified: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        simplified.append(
            {
                "forecastDay": item.get("forecastDay"),
                "dayToWatch": item.get("dayToWatch"),
                "headline": item.get("headline"),
                "observation": item.get("observation"),
            }
        )
    return simplified


def _simplify_rating(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("data", {}).get("rating", [])
    if not isinstance(items, list):
        return []

    simplified: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rating = item.get("rating")
        if not isinstance(rating, dict):
            rating = {}
        simplified.append(
            {
                "timestamp": item.get("timestamp"),
                "utcOffset": item.get("utcOffset"),
                "rating": {
                    "key": rating.get("key"),
                    "value": rating.get("value"),
                },
            }
        )
    return simplified


def _local_day_and_hour(timestamp: int, utc_offset: int) -> tuple[str, int]:
    local_ts = timestamp + (utc_offset * 3600)
    dt = datetime.fromtimestamp(local_ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d"), dt.hour


def _round_for_llm(value: float) -> float:
    return round(value, 2)


def _summarize_ratings(day_ratings: list[dict[str, Any]]) -> dict[str, Any]:
    if not day_ratings:
        return {
            "dominant_key": None,
            "min_value": None,
            "max_value": None,
            "avg_value": None,
        }

    values: list[float] = []
    for item in day_ratings:
        raw_value = item.get("rating", {}).get("value")
        if raw_value is None:
            continue
        try:
            values.append(float(raw_value))
        except (TypeError, ValueError):
            continue
    keys = [r.get("rating", {}).get("key") for r in day_ratings if r.get("rating", {}).get("key")]
    dominant_key = Counter(keys).most_common(1)[0][0] if keys else None

    if not values:
        return {
            "dominant_key": dominant_key,
            "min_value": None,
            "max_value": None,
            "avg_value": None,
        }

    return {
        "dominant_key": dominant_key,
        "min_value": _round_for_llm(min(values)),
        "max_value": _round_for_llm(max(values)),
        "avg_value": _round_for_llm(sum(values) / len(values)),
    }


def _build_rating_windows(day_ratings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Keep one rating per 3-hour bucket to stay compact.
    buckets: dict[int, dict[str, Any]] = {}
    for item in day_ratings:
        ts = item.get("timestamp")
        offset = item.get("utcOffset")
        rating = item.get("rating", {})
        if not isinstance(ts, int) or not isinstance(offset, int):
            continue
        local_day, local_hour = _local_day_and_hour(ts, offset)
        _ = local_day  # local_day already used upstream for grouping.
        bucket = (local_hour // 3) * 3
        existing = buckets.get(bucket)
        if existing is None or ts < existing["timestamp"]:
            buckets[bucket] = {
                "timestamp": ts,
                "local_hour": local_hour,
                "key": rating.get("key"),
                "value": rating.get("value"),
            }

    ordered = [buckets[k] for k in sorted(buckets)]
    for item in ordered:
        item.pop("timestamp", None)
    return ordered


def _merge_daily_forecast(
    conditions: list[dict[str, Any]],
    rating: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ratings_by_day: dict[str, list[dict[str, Any]]] = {}
    for item in rating:
        ts = item.get("timestamp")
        offset = item.get("utcOffset")
        if not isinstance(ts, int) or not isinstance(offset, int):
            continue
        local_day, _ = _local_day_and_hour(ts, offset)
        ratings_by_day.setdefault(local_day, []).append(item)

    daily: list[dict[str, Any]] = []
    for cond in conditions:
        day = cond.get("forecastDay")
        if not isinstance(day, str):
            continue
        day_ratings = ratings_by_day.get(day, [])
        daily.append(
            {
                "forecastDay": day,
                "dayToWatch": cond.get("dayToWatch"),
                "headline": cond.get("headline"),
                "observation": cond.get("observation"),
                "rating_summary": _summarize_ratings(day_ratings),
                "rating_windows": _build_rating_windows(day_ratings),
            }
        )
    return daily


@mcp.tool()
def get_surf_forecast(days: int = DEFAULT_DAYS) -> dict[str, Any]:
    """Fetch Surfline forecast data for one configured spot.

    Uses `SURFLINE_SPOT_ID` from environment and returns both
    `conditions` and `rating` endpoint payloads.
    """
    spot_id = _required_env("SURFLINE_SPOT_ID")
    if days < 1:
        raise RuntimeError("days must be >= 1")

    conditions_raw = _fetch_forecast("conditions", spot_id=spot_id, days=days)
    rating_raw = _fetch_forecast("rating", spot_id=spot_id, days=days)

    conditions = _simplify_conditions(conditions_raw)
    rating = _simplify_rating(rating_raw)

    return {
        "spot_id": spot_id,
        "days": days,
        "daily_forecast": _merge_daily_forecast(conditions, rating),
    }


if __name__ == "__main__":
    mcp.run()
