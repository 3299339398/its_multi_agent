"""保守地规范化口语化用户输入，供路由和检索使用。"""
import re

_FOLLOW = re.compile(r"^(?:那)?(?:它|这个|那个|上述|刚才|上一个)(.*)$")
_SHORT = re.compile(r"^(续航|价格|多少钱|怎么样|如何|原因|怎么解决|地址|电话|路线|耗时|费用)[？?。！!\s]*$")
_CONTINUE = re.compile(r"^(?:继续|接着|然后|再说说|详细说说|展开一下|回到刚才|回到上面|基于上面|按照刚才)(.*)$")
_TOPIC_SWITCH = re.compile(
    r"(?:换个话题|换一个问题|另外问|另一个问题|不说这个了|先不说这个|现在问|我再问一个|顺便问)",
    re.I,
)
_SOURCE_REFERENCE = re.compile(
    r"(?:知识库|知识空间|资料库|内部资料|项目文档|附件|网上|联网|网络|网页).{0,8}"
    r"(?:查|找|搜|核对|确认|检索|查询|看看)|"
    r"(?:查|找|搜|核对|确认|检索|查询|看看).{0,8}"
    r"(?:刚才|上面|前面|这个|上述|相关内容)",
    re.I,
)
_FILLERS = re.compile(r"^(嗯+|呃+|那个|就是|然后|我想问一下|麻烦问一下|请问一下)[，,、：: ]*")
_TAILS = re.compile(r"[，,、 ]*(呗|呢|啊|呀|哈|嘛|吧|哦|诶)[？?。！! ]*$")
_COLLOQUIAL = ((re.compile(r"帮我看下(.+)"), r"请分析\1"),
               (re.compile(r"帮我查下(.+)"), r"请查询\1"),
               (re.compile(r"说下(.+)"), r"请说明\1"),
               (re.compile(r"咋(?:办|整)(.*)"), r"如何处理\1"),
               (re.compile(r"怎么搞(.*)"), r"如何处理\1"),
               (re.compile(r"有啥(.*)"), r"有哪些\1"),
               (re.compile(r"能不能(.*)"), r"是否可以\1"))

def rewrite_query(question: str, history: list[dict] | None = None) -> str:
    text = (question or "").strip()
    if not text:
        return text
    # 规范化各领域的口语表达，但不添加原文不存在的事实。
    text = re.sub(r"\s+", " ", text)
    text = _FILLERS.sub("", text)
    text = _TAILS.sub("", text).strip()
    for pattern, replacement in _COLLOQUIAL:
        normalized = pattern.sub(replacement, text, count=1)
        if normalized != text:
            text = normalized
            break
    text = re.sub(r"(.)\1{2,}", r"\1", text) if not re.search(r"[A-Za-z]", text) else text
    if not history:
        return text
    prior_users = [m.get("content", "").strip() for m in history
                   if m.get("role") == "user" and isinstance(m.get("content"), str) and m.get("content", "").strip()]
    if not prior_users:
        return text
    # 明确换题时必须切断旧任务，避免把旧主题错误带入新问题。
    if _TOPIC_SWITCH.search(text):
        return text
    base = prior_users[-1]
    # 如果用户刚回答了助手的澄清问题，优先使用助手上一轮提出的槽位，
    # 让“郑州”“第二个”“都可以”等短回答能和当前任务建立关系。
    assistants = [m.get("content", "").strip() for m in history
                  if m.get("role") == "assistant" and isinstance(m.get("content"), str)
                  and m.get("content", "").strip()]
    last_assistant = assistants[-1] if assistants else ""
    match = _FOLLOW.match(text)
    if match:
        suffix = match.group(1).strip(" ：:，,。！？!? ")
        return f"关于“{base[:500]}”{suffix or '的这个问题'}"
    continuation = _CONTINUE.match(text)
    if continuation:
        suffix = continuation.group(1).strip(" ：:，,。！？!? ")
        return f"继续讨论“{base[:500]}”{suffix}"
    if _SOURCE_REFERENCE.search(text):
        return f"基于“{base[:500]}”的上下文，{text}"
    if _SHORT.fullmatch(text.rstrip("呢？?。！! ")):
        return f"关于“{base[:500]}”的{text.rstrip('？?。！!')}"
    # 助手刚刚明确提出问题，而用户只给出短答案时，保留助手问题作为关系线索。
    if len(text) <= 32 and last_assistant and re.search(r"[？?]|请问|哪个|哪里|是否|出发|目的地|选择", last_assistant):
        return f"针对助手上一轮澄清（{last_assistant[:300]}），用户补充：{text}；原任务：{base[:300]}"
    # 简短的位置或出行方式回答已由 navigation_context 处理，避免将其改写为误导性检索词。
    return text
