"""Lazy compatibility accessors backed by the shared model profile factory."""

from its_multi_agent.backend.app.infrastructure.ai.model_factory import default_model


def __getattr__(name):
    if name in {"main_model", "sub_model"}:
        return default_model()
    raise AttributeError(name)
