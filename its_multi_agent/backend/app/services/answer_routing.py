"""聊天准备流程与离线评测共用的来源选择策略。"""

import re
from typing import Literal

from pydantic import BaseModel, Field


class RoutePlan(BaseModel):
    route: Literal["direct", "attachment", "knowledge", "web", "mixed", "service", "clarify"]
    knowledge_query: str = Field(default="", max_length=5000)
    web_query: str = Field(default="", max_length=5000)
    knowledge_space: str = Field(default="default", min_length=1, max_length=64, pattern=r"^[\w.-]+$")
    domain: str = Field(default="general", min_length=1, max_length=64, pattern=r"^[\w.-]+$")
    clarification: str = Field(default="", max_length=500)


_PRIVATE = re.compile(
    r"内部|私域|我司|本公司|我们(?:公司|项目|团队)|本项目|客户名单|薪资明细|"
    r"公司.{0,40}(?:制度|报销|差旅|项目|合同|客户|手册|薪酬|交付)|"
    r"\b(?:internal|intranet|our (?:company|project|contract|policy|latest internal))\b",
    re.I,
)
_PUBLIC_SUBJECT = re.compile(
    r"国家.{0,10}(?:政策|法规|税收|法律|规定)|公开(?:政策|法规|资料)|"
    r"官方(?:公告|发布|政策|文档)|天气|股价|汇率|新闻|比赛结果|"
    r"\b(?:weather|stock price|exchange rate|public policy|government)\b", re.I,
)
_LIVE = re.compile(r"今天|当前|现在|最新|近期|实时|\b(?:latest|current|today|recent)\b", re.I)
_WEB = re.compile(r"联网|网上(?:查|搜)|网络搜索|公网|\b(?:search the web|online search)\b", re.I)
_NO_WEB = re.compile(r"(?:不要|禁止|别|无需|不能).{0,4}(?:联网|上网|网络|公网)|"
                     r"(?:只|仅)(?:查|用|依据|根据).{0,5}(?:知识库|附件|内部)|"
                     r"\b(?:do not|don't|no) (?:search|browse|web)\b", re.I)
_ATTACHMENT = re.compile(r"附件|上传|这份(?:文件|文档|资料|合同)|\b(?:attachment|uploaded)\b", re.I)
_FOLLOW_UP = re.compile(r"^(?:那)?(?:它|这个|那个|上述|刚才|上一个)|\b(?:it|that one)\b", re.I)
_SERVICE = re.compile(r"服务站|附近.{0,8}(?:门店|维修|店)|路线|导航|\b(?:navigate|service station)\b", re.I)
_DIRECT = re.compile(
    r"^(?:你是(?:哪个|什么)模型|你是谁|你(?:可以|能|可以用来|能够)(?:做什么|干什么)|你有什么功能|当前(?:使用的)?模型(?:是什么)?)"
    r"[!！。,.，?？\s]*$",
    re.I,
)


def private_question(question: str) -> bool:
    return bool(_PRIVATE.search(question))


def attachment_question(question: str) -> bool:
    return bool(_ATTACHMENT.search(question))


def service_requested(question: str) -> bool:
    return bool(_SERVICE.search(question))


def combined_service_request(question: str) -> bool:
    return service_requested(question) and bool(
        private_question(question) or _PUBLIC_SUBJECT.search(question)
        or re.search(r"故障|蓝屏|诊断|原因|资料|知识库|附件", question)
    )


def identifiers(text: str) -> set[str]:
    """保护明确的型号、错误码和版本标识，不将所有数值都视为标识。"""
    tokens = re.findall(r"(?<![A-Za-z0-9])[A-Za-z0-9]+(?:[-_./][A-Za-z0-9]+)*(?![A-Za-z0-9])", text)
    return {token.casefold() for token in tokens
            if any(c.isalpha() for c in token) and any(c.isdigit() for c in token)
            and not re.fullmatch(r"\d+(?:ms|s|min|h|kg|mm|cm|km|gb|mb|c|f)", token, re.I)}


def protected_conditions(text: str) -> set[str]:
    # 排除控制搜索行为的短语，保留事实数值和运算符。
    text = _NO_WEB.sub("", text)
    text = re.sub(r"没有(?:结果)?就|查不到(?:时|就)?", "", text)
    tokens = re.findall(
        r"\d+(?:[.-]\d+)*|<=|>=|!=|[<>≤≥]|不超过|不少于|不低于|不高于|至少|至多|"
        r"大于|小于|低于|高于|超过|未|没有|不能|不要|禁止|已(?:经)?|"
        r"\b(?:not|without|before|after|above|below|under|over)\b", text, re.I,
    )
    return {token.casefold().replace("已经", "已") for token in tokens}


def clarify(message: str) -> RoutePlan:
    return RoutePlan(route="clarify", clarification=message)


def route_by_rules(question: str, *, has_attachments: bool = False,
                   previous_question: str = "") -> RoutePlan | None:
    text = question.strip()
    if len(text) > 5000:
        return clarify("问题较长，请将资料作为附件提供，并单独说明要查询的问题，以免遗漏条件。")
    if re.fullmatch(r"(?:你好|您好|谢谢|多谢|再见|hello|hi|thanks)[!！。,.，?？\s]*", text, re.I):
        return RoutePlan(route="direct")
    if _FOLLOW_UP.search(text):
        return None if previous_question or has_attachments else clarify("请说明你指的是哪个对象、型号或哪份资料。")
    if re.search(r"知识空间|领域\s*[:：]?\s*[\w.-]+|\b(?:knowledge_space|domain)\b", text, re.I):
        return None
    if combined_service_request(text):
        return None
    private = private_question(text) or attachment_question(text)
    mixed = private and bool(_PUBLIC_SUBJECT.search(text))
    if _ATTACHMENT.search(text) and not _PUBLIC_SUBJECT.search(text):
        return RoutePlan(route="attachment") if has_attachments else clarify("当前对话没有可用附件，请提供要查询的资料。")
    if mixed:
        return None
    if private:
        return RoutePlan(route="knowledge", knowledge_query=text[:5000])
    if _DIRECT.fullmatch(text):
        return RoutePlan(route="direct")
    if "知识库" in text and (_WEB.search(text) or "官方" in text):
        return None
    if _NO_WEB.search(text):
        return None
    if _SERVICE.search(text):
        return RoutePlan(route="service")
    public_release = _LIVE.search(text) and re.search(r"版本|发布|\b(?:release|version)\b", text, re.I)
    if _PUBLIC_SUBJECT.search(text) or _WEB.search(text) or public_release:
        return RoutePlan(route="web", web_query=text[:5000])
    if "知识库" in text:
        return RoutePlan(route="knowledge", knowledge_query=text[:5000])
    return None


def validate_plan(question: str, proposal: RoutePlan, *, has_attachments: bool = False,
                  previous_question: str = "", memory_context: str = "") -> RoutePlan:
    """允许模型判断意图，但不得覆盖明确的来源边界。"""
    fixed = route_by_rules(question, has_attachments=has_attachments, previous_question=previous_question)
    if fixed is not None:
        return fixed
    plan = proposal.model_copy()
    contextual = bool(_FOLLOW_UP.search(question))
    private = (private_question(question) or attachment_question(question)
               or (contextual and (private_question(previous_question) or attachment_question(previous_question))))
    mixed = private and bool(_PUBLIC_SUBJECT.search(question))
    if plan.route == "clarify":
        return clarify(plan.clarification or "请补充要查询的对象、资料来源或版本。")
    scope_context = question + (previous_question + memory_context if contextual else "")
    if ((plan.knowledge_space != "default" and plan.knowledge_space not in scope_context)
            or (plan.domain != "general" and plan.domain not in scope_context)):
        return clarify("请明确知识空间和领域，不能使用未指定的检索范围。")
    if combined_service_request(question) and plan.route not in {"knowledge", "web", "mixed", "attachment"}:
        return clarify("问题同时包含资料查询和地点服务，请明确要先核实的资料问题。")
    if _NO_WEB.search(question) and (plan.route in {"web", "mixed"} or plan.web_query):
        return clarify("已按要求不联网。请提供可用资料，或明确要查询的知识库内容。")
    if private and plan.route not in {"knowledge", "mixed", "attachment"}:
        return clarify("请明确要查询的内部资料或制度名称，公网信息不能代替内部依据。")
    if mixed and plan.route != "mixed":
        return clarify("这个问题同时涉及内部资料和公开信息，请明确两部分要比较的对象。")
    if plan.route == "attachment" and not has_attachments:
        return clarify("当前对话没有可用附件，请提供要查询的资料。")
    if plan.route in {"knowledge", "mixed"} and not plan.knowledge_query.strip():
        return clarify("请明确要查询的文档、制度或产品问题。")
    if plan.route in {"web", "mixed"} and not plan.web_query.strip():
        return clarify("请明确要查询的公开信息。")
    if plan.web_query:
        if private_question(plan.web_query) or _ATTACHMENT.search(plan.web_query):
            return clarify("公开搜索问题包含内部资料，请单独说明需要查询的公开主题。")
        if private and (plan.route != "mixed" or not _PUBLIC_SUBJECT.search(plan.web_query)):
            return clarify("内部资料缺失时不能自动用公网替代，请提供相应内部依据。")
        if private and identifiers(plan.web_query) - identifiers(question):
            return clarify("公开搜索包含未确认的标识，请明确公开查询对象。")
    original_ids = identifiers(question)
    if contextual:
        original_ids |= identifiers(previous_question)
    query_ids = identifiers(plan.knowledge_query + " " + plan.web_query)
    allowed_ids = original_ids | (identifiers(memory_context) if contextual else set())
    if plan.route in {"knowledge", "web", "mixed"} and (not original_ids.issubset(query_ids) or not query_ids.issubset(allowed_ids)):
        return clarify("查询计划中的型号或版本与原问题不一致，请明确需要查询的对象。")
    if plan.route in {"knowledge", "web", "mixed"}:
        original_conditions = protected_conditions(question)
        allowed_conditions = original_conditions | (protected_conditions(previous_question + memory_context) if contextual else set())
        query_conditions = protected_conditions(plan.knowledge_query + " " + plan.web_query)
        if not original_conditions.issubset(query_conditions) or not query_conditions.issubset(allowed_conditions):
            return clarify("查询计划遗漏或改变了数值、条件或已尝试的操作，请明确原始限制后重试。")
    return plan
