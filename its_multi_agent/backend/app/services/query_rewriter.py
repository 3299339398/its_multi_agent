"""保守地规范化口语化用户输入，供路由和检索使用。"""
import re

_FOLLOW = re.compile(r"^(?:那)?(?:它|这个|那个|上述|刚才|上一个)(.*)$")
_SHORT = re.compile(r"^(续航|价格|多少钱|怎么样|如何|原因|怎么解决|地址|电话|路线|耗时|费用)[？?。！!\s]*$")
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
    prior = [m.get("content", "").strip() for m in history
             if m.get("role") == "user" and isinstance(m.get("content"), str) and m.get("content", "").strip()]
    if not prior:
        return text
    base = prior[-1]
    match = _FOLLOW.match(text)
    if match:
        suffix = match.group(1).strip(" ：:，,。！？!? ")
        return f"关于“{base[:500]}”{suffix or '的这个问题'}"
    if _SHORT.fullmatch(text.rstrip("呢？?。！! ")):
        return f"关于“{base[:500]}”的{text.rstrip('？?。！!')}"
    # 简短的位置或出行方式回答已由 navigation_context 处理，避免将其改写为误导性检索词。
    return text
