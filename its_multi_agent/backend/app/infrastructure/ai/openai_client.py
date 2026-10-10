"""基于共享模型配置工厂提供延迟加载的兼容访问接口。"""

from its_multi_agent.backend.app.infrastructure.ai.model_factory import default_model


def __getattr__(name):
    if name in {"main_model", "sub_model"}:
        return default_model()
    raise AttributeError(name)
