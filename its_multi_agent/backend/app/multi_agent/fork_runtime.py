"""缓存友好的父子 Agent 请求模板。

Fork 的边界由应用维护：固定的 instructions、工具顺序和模型配置构成
共享前缀，当前分支的角色、任务和证据只追加到输入末尾。
"""

import copy
import json
from dataclasses import dataclass
from typing import Any

from agents import Agent, ModelSettings

from its_multi_agent.backend.app.infrastructure.ai.prompt_loader import load_prompt


@dataclass(frozen=True)
class ForkTemplate:
    model: Any
    tools: tuple[Any, ...]
    instructions: str
    max_output_tokens: int | None = None

    def build_agent(self, *, mcp_servers=None) -> Agent:
        """用完全相同的固定配置创建父、子 Agent。"""
        return Agent(
            name="知行-Fork-Agent",
            model=self.model,
            instructions=self.instructions,
            tools=list(self.tools),
            model_settings=ModelSettings(
                temperature=0,
                max_tokens=self.max_output_tokens,
            ),
            mcp_servers=list(mcp_servers or ()),
        )

    def branch_input(
        self,
        base_messages: list[dict],
        *,
        branch_role: str,
        task: str,
        instructions: str = "",
        data: dict | None = None,
    ) -> list[dict]:
        """复制共同输入，只在末尾追加本分支的动态内容。"""
        messages = copy.deepcopy(base_messages)
        messages.append({
            "role": "user",
            "content": json.dumps(
                {
                    "type": "fork_branch",
                    "role": branch_role,
                    "task": task,
                    "instructions": instructions,
                    "data": data or {},
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        })
        return messages


def build_fork_template(model, tools, max_output_tokens: int | None = None) -> ForkTemplate:
    """创建本次请求复用的固定 Fork 模板。"""
    return ForkTemplate(
        model=model,
        tools=tuple(tools),
        # 这里只放父子分支都适用的规则；角色提示词属于动态后缀，
        # 否则技术、业务和工程分支会被主调度提示词错误地约束。
        instructions=load_prompt("fork_base"),
        max_output_tokens=max_output_tokens,
    )
