from typing import Any

from its_multi_agent.backend.app.infrastructure.maps.coordinates import to_bd09ll
from its_multi_agent.backend.app.schemas.request import GeoLocation


RELATIVE_LOCATION_MARKERS = (
    "附近", "这里", "这儿", "周围", "周边", "我的位置", "当前位置",
    "所在位置", "我这", "nearby", "here",
)


def normalize_explicit_address(user_input: str) -> str:
    """拒绝相对位置表述，避免将其发送给地理编码服务。"""
    normalized = (user_input or "").strip()
    if any(marker in normalized.lower() for marker in RELATIVE_LOCATION_MARKERS):
        return ""
    return normalized


def device_origin_payload(origin: GeoLocation, original_input: str = "") -> dict[str, Any]:
    longitude, latitude = to_bd09ll(
        origin.longitude,
        origin.latitude,
        origin.coordinate_system,
    )
    return {
        "ok": True,
        "lat": latitude,
        "lng": longitude,
        "source": "device",
        "coordinate_system": "bd09ll",
        "accuracy_meters": origin.accuracy,
        "original_input": original_input,
    }
