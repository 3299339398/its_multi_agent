import json

from agents import OpenAIChatCompletionsModel
from openai import AsyncOpenAI, DefaultAsyncHttpxClient

from its_multi_agent.backend.app.config.settings import settings
from its_multi_agent.backend.app.schemas.model_profile import ModelProfile, ModelRole
from its_multi_agent.backend.app.services.model_endpoint_policy import validate_model_base_url


def _configured_profiles() -> dict[str, ModelProfile]:
    """从 JSON 加载服务端管理的模型配置，密钥始终保留在服务端。"""
    profiles: dict[str, ModelProfile] = {}
    raw = getattr(settings, "MODEL_PROFILES_JSON", "") or ""
    if raw:
        data = json.loads(raw)
        for item in data if isinstance(data, list) else []:
            profile = ModelProfile.model_validate(item)
            profiles[profile.id] = profile

    if settings.AL_BAILIAN_API_KEY and settings.AL_BAILIAN_BASE_URL and (settings.SUB_MODEL_NAME or settings.MAIN_MODEL_NAME):
        profiles.setdefault(
            "default-sub",
            ModelProfile(
                id="default-sub", name="默认问答模型", provider="al-bailian",
                model_name=settings.SUB_MODEL_NAME or settings.MAIN_MODEL_NAME or "",
                base_url=settings.AL_BAILIAN_BASE_URL,
                api_key=settings.AL_BAILIAN_API_KEY,
                roles=("chat", "reasoning"), supports_reasoning=True,
            ),
        )
    if settings.SF_API_KEY and settings.SF_BASE_URL and settings.MAIN_MODEL_NAME:
        profiles.setdefault(
            "default-main",
            ModelProfile(
                id="default-main", name="默认推理模型", provider="silicon-flow",
                model_name=settings.MAIN_MODEL_NAME, base_url=settings.SF_BASE_URL,
                api_key=settings.SF_API_KEY, roles=("reasoning", "chat"),
                supports_reasoning=True,
            ),
        )
    return profiles


def list_profiles() -> list[ModelProfile]:
    return list(_configured_profiles().values())


def resolve_profile(profile_id: str | None, role: ModelRole = "chat") -> ModelProfile:
    profiles = _configured_profiles()
    if profile_id:
        profile = profiles.get(profile_id)
        if profile is None:
            raise ValueError(f"未知模型配置: {profile_id}")
        if role not in profile.roles:
            raise ValueError(f"模型配置 {profile_id} 不支持 {role} 角色")
        return profile
    for profile in profiles.values():
        if role in profile.roles:
            return profile
    raise ValueError(f"未配置可用的 {role} 模型")


def create_model(profile_id: str, model_name: str, base_url: str, api_key: str):
    base_url = validate_model_base_url(base_url, settings)
    client = AsyncOpenAI(api_key=api_key, base_url=base_url,
                         http_client=DefaultAsyncHttpxClient(follow_redirects=False))
    return OpenAIChatCompletionsModel(model=model_name, openai_client=client)


def model_for(profile: ModelProfile):
    return create_model(profile.id, profile.model_name, profile.base_url, profile.api_key)


def default_model():
    return model_for(resolve_profile(None, role="chat"))


def profile_from_temporary(data, profile_id: str = "temporary") -> ModelProfile:
    return ModelProfile(id=profile_id, name=data.name, provider=data.provider,
                        model_name=data.model_name, base_url=validate_model_base_url(data.base_url, settings),
                        api_key=data.api_key, roles=tuple(data.roles),
                        supports_vision="vision" in data.roles,
                        supports_reasoning="reasoning" in data.roles,
                        context_window_tokens=data.context_window_tokens,
                        max_output_tokens=data.max_output_tokens)
