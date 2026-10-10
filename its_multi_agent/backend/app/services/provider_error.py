from __future__ import annotations

from dataclasses import dataclass
import sqlite3


@dataclass(frozen=True)
class ProviderErrorInfo:
    message: str
    retryable: bool


def classify_agent_error(error: Exception) -> ProviderErrorInfo:
    """按实际来源分类故障，避免将所有错误都归因于模型接口。"""
    from its_multi_agent.backend.app.services.attachment_service import AttachmentError
    from its_multi_agent.backend.app.services.context_budget import ContextBudgetError
    from agents.exceptions import MaxTurnsExceeded
    from its_multi_agent.backend.app.infrastructure.tools.local.file_output import FileArtifactGenerationError

    if isinstance(error, FileArtifactGenerationError):
        return ProviderErrorInfo(str(error), False)

    if isinstance(error, MaxTurnsExceeded):
        return ProviderErrorInfo(
            "智能体达到最大执行轮数，任务未完成。请检查所需工具是否已启用并确认授权，或将任务拆分后重试。",
            False,
        )

    if isinstance(error, ContextBudgetError):
        return ProviderErrorInfo(str(error), False)
    if isinstance(error, AttachmentError):
        return ProviderErrorInfo(str(error), False)
    if isinstance(error, sqlite3.Error):
        return ProviderErrorInfo("会话存储暂时不可用，请稍后重试。", False)

    details = _error_details(error).lower()
    if isinstance(error, ValueError):
        if "model base url" in details:
            return ProviderErrorInfo("模型服务地址无效或尚未批准，请选择管理员已批准的地址。", False)
        if "插件" in details:
            return ProviderErrorInfo("所选工具配置无效，请刷新页面后重新选择。", False)
        if "模型" in details or "profile" in details or "json" in details:
            return ProviderErrorInfo("模型配置无效，请检查服务端模型设置。", False)
        return ProviderErrorInfo("请求参数无效，请检查输入后重试。", False)

    error_module = type(error).__module__.split(".", 1)[0]
    has_provider_response = any(
        getattr(error, attribute, None) is not None
        for attribute in ("status_code", "response")
    )
    provider_markers = (
        "api key", "apikey", "quota", "rate limit", "model service",
        "connection error", "openai", "dashscope", "siliconflow",
    )
    if (
        error_module in {"openai", "agents"}
        or has_provider_response
        or any(marker in details for marker in provider_markers)
    ):
        return classify_provider_error(error)

    if isinstance(error, (ConnectionError, TimeoutError)):
        return ProviderErrorInfo("外部服务暂时不可用，请稍后重试。", True)

    return ProviderErrorInfo("系统处理请求时发生异常，请稍后重试。", False)


def classify_provider_error(error: Exception) -> ProviderErrorInfo:
    """将模型服务故障转换为安全的用户提示和重试策略。"""
    status_code = _find_status_code(error)
    details = _error_details(error).lower()

    quota_markers = (
        "quota", "credit", "balance", "allocationquota", "freetier",
        "insufficient funds", "余额不足", "额度",
    )
    auth_markers = (
        "unauthorized", "authentication", "api key", "apikey",
        "invalid key", "permission denied", "鉴权", "认证失败",
    )

    if status_code == 402 or any(marker in details for marker in quota_markers):
        return ProviderErrorInfo(
            "模型服务额度已用完，请更换有效 API Key 或充值后重试。",
            False,
        )
    if status_code in {401, 403} or any(marker in details for marker in auth_markers):
        return ProviderErrorInfo(
            "模型服务鉴权失败，请检查 API Key 和模型访问权限。",
            False,
        )
    if status_code == 400:
        return ProviderErrorInfo(
            "模型服务配置或请求参数无效，请检查当前模型配置。",
            False,
        )

    retryable = (
        status_code is None
        or status_code == 408
        or status_code == 429
        or status_code >= 500
    )
    return ProviderErrorInfo(
        "模型服务暂时不可用，请稍后重试。" if retryable
        else "模型服务请求失败，请检查服务配置。",
        retryable,
    )


def _find_status_code(error: Exception) -> int | None:
    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        direct_status = getattr(current, "status_code", None)
        response = getattr(current, "response", None)
        response_status = getattr(response, "status_code", None)
        for candidate in (direct_status, response_status):
            try:
                if candidate is not None:
                    return int(candidate)
            except (TypeError, ValueError):
                pass
        current = current.__cause__ or current.__context__
    return None


def _error_details(error: Exception) -> str:
    parts: list[str] = []
    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        parts.append(str(current))
        response = getattr(current, "response", None)
        if response is not None:
            parts.append(str(getattr(response, "text", "")))
        current = current.__cause__ or current.__context__
    return " ".join(parts)
