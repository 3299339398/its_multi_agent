from typing import Any

from its_multi_agent.backend.knowledge.utils.text_utils import TextUtils


class HtmlParser:
    """将远端知识库 HTML 记录整理为带稳定章节结构的 Markdown。"""

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def parse_html_to_markdown(
        self, knowledge_no: str, html_data: dict[str, Any]
    ) -> str:
        if not isinstance(html_data, dict):
            raise ValueError("远端知识库记录必须是对象")

        content = self._text(html_data.get("content"))
        if not content:
            raise ValueError("要解析的数据不存在")

        title = self._text(html_data.get("title")) or "暂无标题"
        items = [
            f"# 知识库 {self._text(knowledge_no)}",
            f"## 标题\n{title}",
        ]

        digest = self._text(html_data.get("digest"))
        if digest:
            items.append(f"## 问题描述\n{digest}")

        categories = []
        first_topic = self._text(html_data.get("firstTopicName"))
        sub_topic = self._text(html_data.get("subTopicName"))
        question_category = self._text(html_data.get("questionCategoryName"))
        if first_topic:
            categories.append(f"主类别: {first_topic}")
        if sub_topic:
            categories.append(f"子类别: {sub_topic}")
        elif question_category:
            categories.append(f"问题类别: {question_category}")
        if categories:
            items.append("## 分类\n" + "\n".join(categories))

        keywords = html_data.get("keyWords") or []
        if isinstance(keywords, str):
            keywords = [keywords]
        if isinstance(keywords, (list, tuple)):
            normalized_keywords = []
            for keyword in keywords:
                if isinstance(keyword, str):
                    normalized_keywords.extend(
                        part.strip() for part in keyword.split(",") if part.strip()
                    )
            if normalized_keywords:
                items.append("## 关键词\n" + ", ".join(normalized_keywords))

        metadata = []
        created_at = self._text(html_data.get("createTime"))
        version = self._text(html_data.get("versionNo"))
        if created_at:
            metadata.append(f"创建时间: {created_at}")
        if version:
            metadata.append(f"版本: {version}")
        if metadata:
            items.append("## 元信息\n" + " | ".join(metadata))

        markdown_content = TextUtils.html_to_markdown(content).strip()
        if not markdown_content:
            raise ValueError("HTML 清洗后没有可入库的内容")
        items.append(f"## 解决方案\n{markdown_content}")
        items.append(
            f"<!-- 文档主题：{title} (知识库编号: {self._text(knowledge_no)}) -->"
        )
        return "\n\n".join(items)
