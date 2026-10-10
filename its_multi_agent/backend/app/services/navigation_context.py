"""从会话持久化的近期消息中恢复待补充的导航槽位。

不使用进程级全局状态，避免不同用户、不同会话或服务重启前后的请求共享待处理路线。
遇到无法识别的对话轮次时结束此专用解析流程，其他任务仍由常规规划器接收原始对话。
"""

import re
from dataclasses import dataclass

from its_multi_agent.backend.app.schemas.service_agent import ServiceTask


_NAVIGATION = re.compile(r"路线|导航|怎么走|怎么去|如何去")
_PLACE = r"[\u4e00-\u9fffA-Za-z0-9·]{2,40}"
_DESTINATION = re.compile(r"(?:到|去)(" + _PLACE + r"?)(?=推荐|规划|怎么|如何|的路线|路线|导航|[，。！？、\s]|$)")
_ORIGIN = re.compile(r"从(" + _PLACE + r"?)(?:出发)?(?:到|去)")
_UNKNOWN = {"这里", "我这里", "我这", "当前位置", "哪里", "哪儿", "那里"}
_MODES = {"开车": "driving", "自驾": "driving", "驾车": "driving",
          "步行": "walking", "走路": "walking", "骑行": "riding",
          "公交": "transit", "公共交通": "transit", "高铁": "transit", "火车": "transit"}
_ANY_MODE = {"都可以", "都行", "随便", "不限", "都可", "均可"}
_NOT_PLACE = re.compile(r"你好|谢谢|算了|不用|取消|换个|什么|为什么|怎么样|可以|推荐|帮我|告诉|解释|天气|知识库|模型|你|我|他|她|不|没|再见")


@dataclass
class NavigationContext:
    request: str
    origin: str = ""
    destination: str = ""
    mode: str = ""
    flexible: bool = False

    def task(self) -> ServiceTask:
        constraints = []
        if self.flexible:
            constraints.append("用户出行方式不限；可推荐比较，默认驾车仅是工具默认值，不是用户指定。")
        elif not self.mode:
            constraints.append("用户尚未指定出行方式；不要声称用户选择了驾车。")
        return ServiceTask(
            request=self.query(), origin_hint=self.origin, destination_hint=self.destination,
            transport_mode=self.mode or "driving", needs_navigation=True, constraints=constraints,
        )

    def query(self) -> str:
        mode = "不限，可比较推荐" if self.flexible else (self.mode or "未指定")
        return (f"{self.request}\n当前导航任务：出发地={self.origin or '待补充'}；"
                f"目的地={self.destination or '待补充'}；出行方式={mode}。")


def resolve_navigation_context(question: str, history: list[dict]) -> NavigationContext | None:
    state = None
    last_assistant = ""
    messages = [item for item in history if item.get("role") in {"user", "assistant"}][-40:]
    for item in [*messages, {"role": "user", "content": question}]:
        content = item.get("content")
        if not isinstance(content, str):
            continue
        text = content.strip().strip("。！？!?，, ")
        if item["role"] == "assistant":
            last_assistant = text
            continue
        if len(text) > 3500:
            state = None
            last_assistant = ""
            continue
        destination = _DESTINATION.search(text)
        origin = _ORIGIN.search(text)
        # 此处仅处理纯导航请求；混合检索或服务任务交给现有规划器处理。
        if _NAVIGATION.search(text) and destination and not re.search(r"知识库|附件|内部|制度|服务站|维修|故障", text):
            state = NavigationContext(request=text, destination=destination[1])
            if origin and origin[1] not in _UNKNOWN:
                state.origin = origin[1]
            if state.destination in _UNKNOWN:
                state.destination = ""
            for label, mode in _MODES.items():
                if label in text:
                    state.mode = mode
                    break
        elif state:
            if text in _ANY_MODE:
                if re.search(r"出行|方式|交通|驾车|开车|高铁|公交", last_assistant):
                    state.flexible, state.mode = True, ""
            elif text in _MODES:
                state.mode, state.flexible = _MODES[text], False
            else:
                explicit_origin = re.fullmatch(r"(?:出发地[是为：:]?|我在|从)(" + _PLACE + r")(?:出发)?", text)
                explicit_destination = re.fullmatch(r"(?:目的地[是为：:]?|改去|改到|改成去)(" + _PLACE + r")", text)
                if explicit_origin:
                    state.origin = re.sub(r"出发$", "", explicit_origin[1])
                elif explicit_destination:
                    state.destination = explicit_destination[1]
                elif (re.fullmatch(_PLACE, text) and not _NOT_PLACE.search(text)
                      and text not in _UNKNOWN and text not in _ANY_MODE):
                    # 简短回答只填充未知槽位，不因助手判断错误而覆盖已知目的地。
                    if not state.origin and re.search(r"出发|起点|哪里|哪儿|城市|位置", last_assistant):
                        state.origin = text
                    elif not state.destination and re.search(r"目的地|终点|到哪|去哪", last_assistant):
                        state.destination = text
                    else:
                        state = None
                else:
                    state = None
        last_assistant = ""
    return state
