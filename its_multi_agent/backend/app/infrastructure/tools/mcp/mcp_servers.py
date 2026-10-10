from agents.mcp import MCPServer, MCPServerStreamableHttp, MCPServerSse, create_static_tool_filter
from mcp.types import ListPromptsResult
from its_multi_agent.backend.app.config.settings import settings
from its_multi_agent.backend.app.services.agent_hooks import AgentPolicyDenied, agent_hooks, tool_allowed
import asyncio
import json
from typing import Dict,Any

# 仅开放业务提示词中明确使用的查询/路线工具；不开放 IP 定位或以后新增的工具。
MAP_MCP_TOOL_NAMES = frozenset({
    "map_search_places", "map_geocode", "map_directions",
    "map_directions_matrix", "map_uri",
})

MAP_LOCAL_TOOL_NAMES = frozenset({
    "resolve_user_location_from_text", "query_nearest_repair_shops_by_coords",
})

search_mcp_client = MCPServerStreamableHttp(
    name="DashScope Search MCP",
    params={
        "url": settings.DASHSCOPE_BASE_URL,
        "headers": {
            "Authorization": f"Bearer {settings.DASHSCOPE_API_KEY or settings.AL_BAILIAN_API_KEY}"
        },
        "timeout": 10,
    },
    cache_tools_list=True,
    tool_filter=create_static_tool_filter(allowed_tool_names=["bailian_web_search"]),
    # SDK 对调用异常退避重试；仅给无写入副作用的查询设置有限次数。
    max_retry_attempts=2,
    retry_backoff_seconds_base=0.5,
)


# 2. 定义百度地图相关的MCP客户端(AK)

baidu_mcp_client = MCPServerSse(
    name="百度地图",
    params={  # https://mcp.map.baidu.com/sse?ak=您的ak
        "url": f"https://mcp.map.baidu.com/sse?ak={settings.BAIDUMAP_AK}",
        "timeout": 10,
        "sse_read_timeout": 60 * 30  # 客户端接收mcp服务端接收数据（数据包）的最大等待时间（大一些）
    },
    client_session_timeout_seconds=20,
    cache_tools_list=True,
    tool_filter=create_static_tool_filter(allowed_tool_names=sorted(MAP_MCP_TOOL_NAMES)),
    max_retry_attempts=2,
    retry_backoff_seconds_base=0.5,
)


class RequestScopedMapServer(MCPServer):
    """共享 MCP 连接，但把暴露范围和每次执行绑定到当前子任务权限。"""

    def __init__(self, context):
        super().__init__()
        self.context = context

    @property
    def name(self):
        return baidu_mcp_client.name

    def _permitted(self, tool_name):
        confirmed = getattr(self.context, "confirmed_tools", frozenset()) or frozenset()
        return (tool_name in MAP_MCP_TOOL_NAMES
                and tool_allowed(self.context, tool_name)
                and tool_name in confirmed)

    async def connect(self):
        # 连接生命周期归启动时的 MCP manager 管理，不能让并发子任务重复连接。
        return None

    async def cleanup(self):
        # 子任务结束不能关闭其他请求正在使用的共享连接。
        return None

    async def list_tools(self, run_context=None, agent=None):
        if not any(self._permitted(name) for name in MAP_MCP_TOOL_NAMES):
            return []
        tools = await baidu_mcp_client.list_tools(run_context, agent)
        return [tool for tool in tools if self._permitted(tool.name)]

    async def call_tool(self, tool_name, arguments, meta=None):
        if not self._permitted(tool_name):
            raise AgentPolicyDenied("当前分支未获准或未确认此地图工具")
        payload = {
            "tool_name": tool_name, "user_id": self.context.user_id,
            "run_id": self.context.run_id, "context": self.context,
        }
        await agent_hooks.authorize_tool(payload)
        await agent_hooks.emit("tool_call", payload)
        try:
            result = await baidu_mcp_client.call_tool(tool_name, arguments, meta=meta)
        except Exception:
            await agent_hooks.emit("tool_output", {**payload, "status": "error"})
            raise
        await agent_hooks.emit("tool_output", {
            **payload, "status": "error" if getattr(result, "isError", False) else "ok",
        })
        return result

    async def list_prompts(self):
        return ListPromptsResult(prompts=[])

    async def get_prompt(self, name, arguments=None):
        raise AgentPolicyDenied("地图子任务不提供 MCP 提示词访问")


def map_mcp_client_for(context):
    """为当前 Agent 分支创建带权限上下文的地图 MCP 视图。"""
    return RequestScopedMapServer(context)



















# ==============================================================================
# 3. 通用测试执行器 (新增：列出工具 -> 查看参数 -> 调用)
# ==============================================================================
async def run_mcp_call(
        mcp_instance: MCPServerSse,
        tool_name: str,
        tool_args: Dict[str, Any]
):
    """
    执行流程：连接 -> 列出所有工具(看参数) -> 调用指定工具 -> 打印结果 -> 断开
    """
    server_name = mcp_instance.name
    print(f"\n{'=' * 60}")
    print(f" [测试启动] 服务: {server_name}")
    print(f"{'=' * 60}")

    try:
        # --- 1. 连接 ---
        print(f" [连接] 正在连接服务器...")
        await mcp_instance.connect()
        print(f" [连接] 成功")

        # --- 2. 列出工具  mcp服务下有多少个工具---
        print(f"\n [列表] 正在获取工具列表及参数定义...")
        tools_list = await mcp_instance.list_tools()

        if tools_list:
            print(f"   发现 {len(tools_list)} 个工具：")
            for i, tool in enumerate(tools_list, 1):
                print(f"\n    [{i}] 工具名: {tool.name}")
                print(f"       描述: {tool.description}")
                print(f"       参数定义 (Schema):")
                # 使用 indent=2 让参数结构清晰可见(inputSchema:工具参数（字典）)
                print(json.dumps(tool.inputSchema, indent=2, ensure_ascii=False))
        else:
            print("    未获取到工具列表")

        print(f"\n{'-' * 40}")

        # # --- 3. 调用工具 ---

        print(f"    发送参数: {json.dumps(tool_args, ensure_ascii=False)}")

        # 执行核心调用（调用mcp服务中某一个工具）
        result = await mcp_instance.call_tool(tool_name, tool_args)
        print(f"\n [响应] 服务器返回结果:")

        # --- 4. 打印结果 ---
        for content in result.content:
            if hasattr(content, 'text'):
                # 尝试解析 JSON 字符串以便美化打印
                # json_res = json.loads(content.text)
                # print(json.dumps(json_res, indent=2, ensure_ascii=False))
                json_res = content.text
                print(json_res)
            else:
                print(f" [Non-Text]: {content}")

    except Exception as e:
        print(f"\n [异常] 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        # --- 5. 清理 ---
        print(f"\n [断开] 正在清理连接...")
        await mcp_instance.cleanup()
        print(f" {server_name} 测试结束\n")


# ==============================================================================
# 4. 分别封装的测试函数
# ==============================================================================

async def test_bailian_search():
    """
    测试百炼搜索 (使用全局 search_mcp)
    """
    await run_mcp_call(
        mcp_instance=search_mcp_client,
        tool_name="bailian_web_search",  # 准备测试联网搜索工具
        tool_args={"query": "小米公司今天的股价如何?"}  # query
    )


async def test_baidu_map():
    """
    测试百度地图 (使用全局 baidu_mcp)
    """
    # await run_mcp_call(
    #     mcp_instance=baidu_map_mcp,
    #     tool_name="map_geocode",  # (地理位置编码)
    #     tool_args={
    #         "address": "北京市昌平区",
    #     }
    # )

    await run_mcp_call(
        mcp_instance=baidu_mcp_client,
        tool_name="map_ip_location",  # (根据ip获取经纬度)
        tool_args={
            "ip": "123.120.109.232",
        }
    )

    await run_mcp_call(
        mcp_instance=baidu_mcp_client,
        tool_name="map_uri",  # (拉起百度地图页面)
        tool_args={
            "service": "direction"
        }
    )


# ==============================================================================
# 5. 主程序入口
# ==============================================================================
async def main():
    # 你可以在这里注释掉不需要跑的测试

    # 任务 1
    # await test_bailian_search()

    # 任务 2
    await test_baidu_map()


if __name__ == '__main__':
    asyncio.run(main())
