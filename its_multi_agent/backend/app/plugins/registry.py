from .manifest import PluginManifest


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, PluginManifest] = {}

    def register(self, manifest: PluginManifest) -> None:
        if manifest.id in self._plugins:
            raise ValueError(f"插件已注册: {manifest.id}")
        self._plugins[manifest.id] = manifest

    def list_plugins(self) -> list[PluginManifest]:
        return list(self._plugins.values())

    def resolve_tools(self, enabled_plugins: list[str] | None = None) -> list[str]:
        selected = set(enabled_plugins) if enabled_plugins is not None else {
            plugin.id for plugin in self._plugins.values() if plugin.enabled_by_default
        }
        unknown = selected.difference(self._plugins)
        if unknown:
            raise ValueError(f"未知插件: {', '.join(sorted(unknown))}")
        tools: list[str] = []
        for plugin in self._plugins.values():
            if plugin.id in selected:
                tools.extend(tool for tool in plugin.tools if tool not in tools)
        return tools


plugin_registry = PluginRegistry()
plugin_registry.register(PluginManifest(
    id="knowledge", name="知识库", description="查询企业私域文档并生成带来源的回答",
    tools=("query_knowledge",),
    capabilities=("retrieval", "question_answering"),
))
plugin_registry.register(PluginManifest(
    id="search", name="联网搜索", description="获取实时新闻、天气和公开网络信息",
    tools=("search_web",), capabilities=("web_search",),
))
plugin_registry.register(PluginManifest(
    id="map", name="地图与服务站", description="地点解析、附近服务站查询和路线规划",
    tools=("query_service_station_and_navigate",), capabilities=("location", "navigation"),
    requires_confirmation=True,
))
plugin_registry.register(PluginManifest(
    id="files", name="文件输出", description="生成受限的文本、Markdown、JSON 或 CSV 文件",
    tools=("create_file",), capabilities=("file_output",), enabled_by_default=False,
))
