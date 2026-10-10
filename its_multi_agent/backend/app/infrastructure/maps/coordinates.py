import math


_PI = math.pi
_AXIS = 6378245.0
_ECCENTRICITY_SQUARED = 0.00669342162296594323
_X_PI = _PI * 3000.0 / 180.0


def is_in_china(longitude: float, latitude: float) -> bool:
    return 73.66 <= longitude <= 135.05 and 3.86 <= latitude <= 53.55


def wgs84_to_gcj02(longitude: float, latitude: float) -> tuple[float, float]:
    """将中国大陆范围内的 GPS WGS84 坐标转换为 GCJ02 坐标。"""
    if not is_in_china(longitude, latitude):
        return longitude, latitude

    delta_lat = _transform_lat(longitude - 105.0, latitude - 35.0)
    delta_lng = _transform_lng(longitude - 105.0, latitude - 35.0)
    rad_lat = latitude / 180.0 * _PI
    magic = math.sin(rad_lat)
    magic = 1 - _ECCENTRICITY_SQUARED * magic * magic
    sqrt_magic = math.sqrt(magic)
    delta_lat = (
        delta_lat * 180.0
        / ((_AXIS * (1 - _ECCENTRICITY_SQUARED)) / (magic * sqrt_magic) * _PI)
    )
    delta_lng = (
        delta_lng * 180.0
        / (_AXIS / sqrt_magic * math.cos(rad_lat) * _PI)
    )
    return longitude + delta_lng, latitude + delta_lat


def gcj02_to_bd09(longitude: float, latitude: float) -> tuple[float, float]:
    z = math.sqrt(longitude * longitude + latitude * latitude) + 0.00002 * math.sin(
        latitude * _X_PI
    )
    theta = math.atan2(latitude, longitude) + 0.000003 * math.cos(longitude * _X_PI)
    return z * math.cos(theta) + 0.0065, z * math.sin(theta) + 0.006


def wgs84_to_bd09(longitude: float, latitude: float) -> tuple[float, float]:
    gcj_lng, gcj_lat = wgs84_to_gcj02(longitude, latitude)
    return gcj02_to_bd09(gcj_lng, gcj_lat)


def to_bd09ll(
    longitude: float,
    latitude: float,
    coordinate_system: str,
) -> tuple[float, float]:
    normalized = coordinate_system.lower()
    if normalized == "bd09ll":
        return longitude, latitude
    if normalized == "gcj02":
        return gcj02_to_bd09(longitude, latitude)
    if normalized == "wgs84":
        return wgs84_to_bd09(longitude, latitude)
    raise ValueError(f"Unsupported coordinate system: {coordinate_system}")


def bd09mc_to_bd09(longitude: float, latitude: float) -> tuple[float, float]:
    """将百度墨卡托坐标转换为百度经纬度坐标。"""
    if abs(latitude) < 1e-6 or abs(longitude) < 1e-6:
        return 0.0, 0.0
    lng = longitude / 20037508.34 * 180
    lat = latitude / 20037508.34 * 180
    lat = 180 / _PI * (2 * math.atan(math.exp(lat * _PI / 180)) - _PI / 2)
    return lng, lat


def _transform_lat(longitude: float, latitude: float) -> float:
    value = (
        -100.0
        + 2.0 * longitude
        + 3.0 * latitude
        + 0.2 * latitude * latitude
        + 0.1 * longitude * latitude
        + 0.2 * math.sqrt(abs(longitude))
    )
    value += (20.0 * math.sin(6.0 * longitude * _PI) + 20.0 * math.sin(2.0 * longitude * _PI)) * 2.0 / 3.0
    value += (20.0 * math.sin(latitude * _PI) + 40.0 * math.sin(latitude / 3.0 * _PI)) * 2.0 / 3.0
    value += (160.0 * math.sin(latitude / 12.0 * _PI) + 320 * math.sin(latitude * _PI / 30.0)) * 2.0 / 3.0
    return value


def _transform_lng(longitude: float, latitude: float) -> float:
    value = (
        300.0
        + longitude
        + 2.0 * latitude
        + 0.1 * longitude * longitude
        + 0.1 * longitude * latitude
        + 0.1 * math.sqrt(abs(longitude))
    )
    value += (20.0 * math.sin(6.0 * longitude * _PI) + 20.0 * math.sin(2.0 * longitude * _PI)) * 2.0 / 3.0
    value += (20.0 * math.sin(longitude * _PI) + 40.0 * math.sin(longitude / 3.0 * _PI)) * 2.0 / 3.0
    value += (150.0 * math.sin(longitude / 12.0 * _PI) + 300.0 * math.sin(longitude / 30.0 * _PI)) * 2.0 / 3.0
    return value
