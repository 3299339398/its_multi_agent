"""Fetch remote knowledge articles and save them as Markdown source files."""

import argparse
import logging
import os
import time
from pathlib import Path
from uuid import uuid4

from its_multi_agent.backend.knowledge.config.settings import settings
from its_multi_agent.backend.knowledge.services.crawler.client import KnowledgeApiClient
from its_multi_agent.backend.knowledge.services.crawler.parser import HtmlParser
from its_multi_agent.backend.knowledge.utils.text_utils import TextUtils


logger = logging.getLogger(__name__)


def _save_markdown(output_dir: Path, filename: str, content: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / filename
    temporary = output_dir / f".{filename}.{uuid4().hex}.tmp"
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="按编号抓取远端知识文章并保存为 Markdown"
    )
    parser.add_argument("--start", type=int, default=1, help="起始知识编号（包含）")
    parser.add_argument("--end", type=int, default=1000, help="结束知识编号（包含）")
    parser.add_argument("--delay", type=float, default=0.2, help="请求之间的等待秒数")
    parser.add_argument("--retries", type=int, default=3, help="每篇文章的最大请求次数")
    parser.add_argument("--timeout", type=float, default=10.0, help="单次请求超时秒数")
    parser.add_argument(
        "--output-dir", type=Path, default=Path(settings.CRAWL_OUTPUT_DIR)
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.start < 1 or args.end < args.start:
        print("编号范围无效：要求 1 <= start <= end。")
        return 2
    if args.delay < 0 or args.retries < 1 or args.timeout <= 0:
        print("延迟不能为负数，重试次数和请求超时必须大于 0。")
        return 2

    parser = HtmlParser()
    success = 0
    failed = 0
    total = args.end - args.start + 1
    for index, knowledge_no in enumerate(range(args.start, args.end + 1), start=1):
        print(f"[{index}/{total}] 获取知识编号 {knowledge_no}")
        for attempt in range(1, args.retries + 1):
            try:
                record = KnowledgeApiClient.fetch_knowledge_content(
                    str(knowledge_no),
                    timeout=args.timeout,
                )
                markdown = parser.parse_html_to_markdown(str(knowledge_no), record)
                title = str(record.get("title") or "无标题").strip()
                clean_title = (
                    TextUtils.clean_filename(title)[:50].rstrip(" ._") or "无标题"
                )
                filename = f"{knowledge_no:04d}-{clean_title}.md"
                _save_markdown(args.output_dir, filename, markdown)
                success += 1
                print(f"  保存成功：{filename}")
                break
            except (OSError, RuntimeError, ValueError, TypeError) as error:
                if attempt == args.retries:
                    failed += 1
                    logger.warning("知识编号 %s 抓取失败: %s", knowledge_no, error)
                    print(f"  抓取失败：{error}")
                elif args.delay:
                    time.sleep(args.delay * attempt)
        if index < total and args.delay:
            time.sleep(args.delay)

    print(f"抓取完成：成功 {success}，失败 {failed}。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
