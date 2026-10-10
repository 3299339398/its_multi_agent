from its_multi_agent.backend.app.infrastructure.logging.logger import logger
from its_multi_agent.backend.app.infrastructure.tools.mcp.mcp_servers import (
    search_mcp_client,
    baidu_mcp_client,
)

# 仅记录连接状态，不将服务商错误或凭据写入 Prompt。
connection_status = {"search_web": "unknown", "query_service_station_and_navigate": "unknown"}

async def mcp_connect():
    # 建立MCP连接
    try:
        await baidu_mcp_client.connect()
        connection_status["query_service_station_and_navigate"] = "connected"
    except Exception as e:
        connection_status["query_service_station_and_navigate"] = "unavailable"
        logger.error(f"百度地图MCP连接失败: {str(e)}")
    try:
        await search_mcp_client.connect()
        connection_status["search_web"] = "connected"
    except Exception as e:
        connection_status["search_web"] = "unavailable"
        logger.error(f"搜索MCP连接失败: {str(e)}")


async def mcp_cleanup():
    # 清理MCP连接
    try:
        await baidu_mcp_client.cleanup()
    except Exception as e:
        logger.warning(f"百度地图MCP清理时出现非致命错误: {e}")
    try:
        await search_mcp_client.cleanup()
    except Exception as e:
        logger.warning(f"搜索MCP清理时出现非致命错误: {e}")
