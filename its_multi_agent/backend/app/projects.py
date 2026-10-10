from dataclasses import dataclass

from its_multi_agent.backend.app.plugins import plugin_registry


@dataclass(frozen=True)
class ProjectManifest:
    id: str
    name: str
    description: str
    plugins: tuple[str, ...]


PROJECTS = (
    ProjectManifest(
        id="default", name="默认项目", description="通用智能服务工具集",
        plugins=tuple(plugin.id for plugin in plugin_registry.list_plugins()),
    ),
)


def list_projects() -> list[ProjectManifest]:
    return list(PROJECTS)


def get_project(project_id: str | None, user_id: str | None = None) -> ProjectManifest:
    selected = project_id or "default"
    if user_id:
        from its_multi_agent.backend.app.repositories.sqlite_workspace_repository import workspace_repository
        row = (workspace_repository.upsert_default(
            user_id, [p.id for p in plugin_registry.list_plugins()]
        ) if selected == "default" else workspace_repository.get(user_id, selected))
        if row:
            import json
            return ProjectManifest(row["id"], row["name"], row["description"], tuple(json.loads(row["plugins_json"] or "[]")))
    for project in PROJECTS:
        if project.id == selected:
            return project
    raise ValueError(f"未知项目: {selected}")
