from its_multi_agent.backend.app.infrastructure.database.database_pool import pool
import json
from pymysql.cursors import DictCursor
from agents import RunContextWrapper, function_tool
from its_multi_agent.backend.app.infrastructure.tools.mcp.mcp_servers import map_mcp_client_for
from its_multi_agent.backend.app.infrastructure.logging.logger import logger
from its_multi_agent.backend.app.infrastructure.maps.origin import (
    device_origin_payload,
    normalize_explicit_address,
)
from its_multi_agent.backend.app.schemas.agent_context import AgentRequestContext
from its_multi_agent.backend.app.schemas.tool import LocationToolRequest, RepairShopToolRequest
from its_multi_agent.backend.app.services.agent_hooks import (
    agent_hooks, AgentPolicyDenied, tool_allowed, tool_confirmed,
)


@function_tool
async def resolve_user_location_from_text(
        ctx: RunContextWrapper[AgentRequestContext],
        user_input: str,
) -> str:
    """
    智能解析用户当前位置（起点），用于导航或服务站查询。
    ⚠️ 注意：
    - 仅用于获取**起点**，不可作为终点使用。

    Args:
        user_input (str): 用户提到的**明确地名**。⚠️重要：如果用户只说了“附近”、“这里”、“我的位置”等相对方位词，请**留空**此参数（传空字符串），不要填入这些词。

    返回 JSON 字符串：
    {
        "ok": bool,
        "lat": float,
        "lng": float,
        "source": "geocode" | "device",
        "original_input": str,
        "error": str?  # 仅当 ok=False 时存在
    }
    """

    try:
        if not tool_allowed(ctx.context, "resolve_user_location_from_text"):
            return json.dumps({"ok": False, "code": "policy_denied", "error": "当前分支未启用位置解析"}, ensure_ascii=False)
        if not tool_confirmed(ctx.context, "resolve_user_location_from_text"):
            return json.dumps({"ok": False, "code": "confirmation_required", "error": "位置服务尚未获得用户确认"}, ensure_ascii=False)
        request = LocationToolRequest(user_input=user_input)
        await agent_hooks.authorize_tool({"tool_name": "resolve_user_location_from_text", "user_input": user_input,
                                          "user_id": ctx.context.user_id, "run_id": ctx.context.run_id,
                                          "context": ctx.context})
    except AgentPolicyDenied as error:
        return json.dumps({"ok": False, "code": "policy_denied", "error": str(error)}, ensure_ascii=False)
    except Exception:
        return json.dumps({"ok": False, "code": "invalid_request", "error": "位置参数无效"}, ensure_ascii=False)
    user_input = request.user_input
    original_input = user_input
    user_input = normalize_explicit_address(user_input)

    # 3.  尝试 Geocode（明确地名解）
    if user_input:
        try:
            logger.debug(f"[Location] Trying geocode for: '{user_input}'")

            # 3.1 调用MCP工具 百度地理编码
            geo_result = await map_mcp_client_for(ctx.context).call_tool(
                tool_name="map_geocode", arguments={"address": user_input}
            )

            # 3.2 MCP 返回的复杂结构
            text = json.loads(geo_result.content[0].text)
            result = text.get("result", {})
            location = result.get("location", {}) if isinstance(result, dict) else {}

            # 3.3  校验返回数据的完整性
            if "lat" in location and "lng" in location:
                lat = float(location["lat"])
                lng = float(location["lng"])
                RepairShopToolRequest(lat=lat, lng=lng)
                logger.info(f"[Location] Geocode success: '{user_input}' → ({lat}, {lng})")
                return json.dumps({
                    "ok": True,
                    "lat": lat,
                    "lng": lng,
                    "source": "geocode",
                    "original_input": original_input
                }, ensure_ascii=False)
            else:
                logger.warning(f"[Location] Geocode returned invalid result: {geo_result}")
        except Exception as e:
            # 3.4 如果 Geocode 报错，不抛出异常，而是吞掉错误继续向下走 IP 逻辑
            logger.warning(f"[Location] Geocode failed for '{user_input}': {e}")

    # 4. 使用本次请求携带的用户授权设备位置。位置只存在于运行上下文，
    # 不进入提示词或会话历史，也不会在并发用户之间共享。
    device_origin = ctx.context.origin
    if device_origin is not None:
        try:
            payload = device_origin_payload(device_origin, original_input)
            logger.info(
                "[Location] Device location converted %s -> BD09LL (%.6f, %.6f), accuracy=%s",
                device_origin.coordinate_system,
                payload["lat"],
                payload["lng"],
                device_origin.accuracy,
            )
            return json.dumps(payload, ensure_ascii=False)
        except Exception as e:
            logger.warning("[Location] Device coordinate conversion failed: %s", e)

    logger.info("[Location] No usable explicit address or device location")
    return json.dumps({
        "ok": False,
        "code": "location_required",
        "error": "无法确定出发位置，请让用户授权设备定位或提供明确的出发地",
        "source": "unavailable",
        "original_input": original_input,
    }, ensure_ascii=False)


@function_tool
def query_nearest_repair_shops_by_coords(
        ctx: RunContextWrapper[AgentRequestContext],
        lat: float,
        lng: float,
        limit: int = 3,
        brand: str = "",
        repair_type: str = "",
) -> str:
    """
    根据给定的经纬度坐标，查询数据库中最近的维修站/服务站。

    Args:
        lat (float): 纬度 (BD09LL)
        lng (float): 经度 (BD09LL)
        limit (int): 返回结果数量限制，默认为 3
        brand (str): 可选品牌，例如联想、华为、苹果
        repair_type (str): 可选维修类型，例如笔记本、手机、换屏

    Returns:
        str: JSON 格式的查询结果，包含最近的维修站列表。
    """
    try:
        if not tool_allowed(ctx.context, "query_nearest_repair_shops_by_coords"):
            return json.dumps({"ok": False, "code": "policy_denied", "error": "当前分支未启用服务站查询"}, ensure_ascii=False)
        if not tool_confirmed(ctx.context, "query_nearest_repair_shops_by_coords"):
            return json.dumps({"ok": False, "code": "confirmation_required", "error": "服务站查询尚未获得用户确认"}, ensure_ascii=False)
        request = RepairShopToolRequest(
            lat=lat, lng=lng, limit=limit, brand=brand, repair_type=repair_type,
        )
        agent_hooks.authorize_tool_sync({"tool_name": "query_nearest_repair_shops_by_coords", "lat": lat, "lng": lng,
                                         "limit": limit, "brand": brand, "repair_type": repair_type,
                                         "context": ctx.context})
    except AgentPolicyDenied as error:
        return json.dumps({"ok": False, "code": "policy_denied", "error": str(error)}, ensure_ascii=False)
    except Exception:
        return json.dumps({"ok": False, "code": "invalid_request", "error": "服务站查询参数无效"}, ensure_ascii=False)
    lat, lng, limit, brand, repair_type = (
        request.lat, request.lng, request.limit, request.brand, request.repair_type,
    )
    connection = None
    cursor = None
    try:
        connection = pool.connection()
        cursor = connection.cursor(DictCursor)

        # 1. Haversine 距离计算公式
        # 6371 是地球平均半径 (km)
        # acos/cos/sin/radians 是三角函数
        # 作用：给定两点坐标代入球面几何公式，算出它们在地球表面的直线距离（公里），并以此作为 distance_km 字段返回
        # 6371 把计算出来的“弧度角度”转化为实际的“地面距离”
        # radians()：经纬度通常是 角度 (Degrees) 三角函数必须使用 弧度 (Radians)

        brand = brand.strip()
        repair_type = repair_type.strip()
        sql = """
        SELECT
            id,
            service_station_name,
            province,
            city,
            district,
            address,
            phone,
            manager,
            manager_phone,
            opening_hours,
            repair_types,
            repair_specialties,
            repair_services,
            supported_brands,
            rating,
            established_year,
            employee_count,
            service_station_description,
            latitude,
            longitude,
            (
                6371 * acos(GREATEST(-1, LEAST(1,
                    cos(radians(%s)) * cos(radians(latitude)) *
                    cos(radians(longitude) - radians(%s)) +
                    sin(radians(%s)) * sin(radians(latitude))
                )))
            ) AS distance_km
        FROM repair_shops
        WHERE 
            latitude IS NOT NULL 
            AND longitude IS NOT NULL
            AND ABS(latitude) <= 90
            AND ABS(longitude) <= 180
            AND (%s = '' OR supported_brands LIKE %s OR service_station_name LIKE %s)
            AND (%s = '' OR repair_types LIKE %s OR repair_specialties LIKE %s OR repair_services LIKE %s)
        ORDER BY distance_km ASC
        LIMIT %s
        """

        brand_pattern = f"%{brand}%"
        repair_pattern = f"%{repair_type}%"
        cursor.execute(sql, (
            lat, lng, lat,
            brand, brand_pattern, brand_pattern,
            repair_type, repair_pattern, repair_pattern, repair_pattern,
            limit,
        ))
        rows = cursor.fetchall()

        logger.info(f"[NearestShops] Found {len(rows)} shops near ({lat}, {lng})")

        return json.dumps({
            "ok": True,
            "count": len(rows),
            "data": rows,
            "query": {
                "lat": lat,
                "lng": lng,
                "limit": limit
            }
        }, ensure_ascii=False, default=str)

    except Exception:
        logger.exception("[NearestShops] DB query failed")
        return json.dumps({
            "ok": False,
            "code": "service_unavailable",
            "error": "服务站查询暂时不可用",
            "query": {"lat": lat, "lng": lng, "limit": limit}
        }, ensure_ascii=False)
    finally:
        # 必须确保归还连接到连接池，否则会导致连接耗尽
        if cursor:
            cursor.close()
        if connection:
            connection.close()
