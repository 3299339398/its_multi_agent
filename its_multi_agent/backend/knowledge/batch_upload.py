"""Submit local Markdown files to the authenticated knowledge ingestion API."""

import argparse
import os
import sys
import time
from pathlib import Path

import requests


DEFAULT_SOURCE_DIR = Path(__file__).resolve().parent / "data" / "crawl"
DEFAULT_BASE_URL = "http://127.0.0.1:8001"
TERMINAL_SUCCESS = {"success", "completed"}
TERMINAL_FAILURE = {"failed", "failure", "error"}


def _request_with_retries(
    request,
    *,
    attempts: int,
    retry_delay: float,
    sleep,
    deadline=None,
    monotonic=time.monotonic,
):
    for attempt in range(attempts):
        if deadline is not None and monotonic() >= deadline:
            raise TimeoutError("request deadline exceeded")
        try:
            response = request()
        except requests.RequestException:
            if attempt + 1 >= attempts:
                raise
        else:
            if response.status_code < 500 and response.status_code != 429:
                return response
            if attempt + 1 >= attempts:
                return response
        delay = retry_delay * (attempt + 1)
        if deadline is not None:
            delay = min(delay, max(0, deadline - monotonic()))
        sleep(delay)
    raise RuntimeError("request retry loop ended unexpectedly")


def wait_for_task(
    session: requests.Session,
    base_url: str,
    task_id: str,
    *,
    poll_interval: float,
    task_timeout: float,
    attempts: int,
    retry_delay: float,
    sleep=time.sleep,
    monotonic=time.monotonic,
) -> tuple[bool, str]:
    deadline = monotonic() + task_timeout
    task_url = f"{base_url.rstrip('/')}/tasks/{task_id}"

    while monotonic() < deadline:
        try:
            response = _request_with_retries(
                lambda: session.get(
                    task_url,
                    timeout=max(0.001, min(30, deadline - monotonic())),
                ),
                attempts=attempts,
                retry_delay=retry_delay,
                sleep=sleep,
                deadline=deadline,
                monotonic=monotonic,
            )
        except requests.RequestException as error:
            return False, f"查询任务请求失败：{error}"
        except TimeoutError:
            return False, f"等待入库超时（{task_timeout:g} 秒），任务 ID: {task_id}"
        if response.status_code != 200:
            return False, f"查询任务失败（HTTP {response.status_code}）"
        try:
            task = response.json()
        except ValueError:
            return False, "任务接口返回了无效 JSON"
        if not isinstance(task, dict):
            return False, "任务接口返回了无效数据"

        status = str(task.get("status", "")).lower()
        if status in TERMINAL_SUCCESS:
            return True, str(task.get("message") or "入库完成")
        if status in TERMINAL_FAILURE:
            detail = task.get("error_message") or task.get("message") or "未知错误"
            return False, f"入库失败：{detail}"
        if status not in {"queued", "processing", "running", "pending"}:
            return False, f"未知任务状态：{status or '空'}"
        sleep(min(poll_interval, max(0, deadline - monotonic())))

    return False, f"等待入库超时（{task_timeout:g} 秒），任务 ID: {task_id}"


def upload_file(
    session: requests.Session,
    file_path: Path,
    base_url: str,
    *,
    knowledge_space: str,
    domain: str,
    poll_interval: float,
    task_timeout: float,
    attempts: int,
    retry_delay: float,
    sleep=time.sleep,
    monotonic=time.monotonic,
) -> tuple[bool, str]:
    upload_url = f"{base_url.rstrip('/')}/upload"

    def submit():
        with file_path.open("rb") as source:
            return session.post(
                upload_url,
                files={"file": (file_path.name, source, "text/markdown")},
                data={"knowledge_space": knowledge_space, "domain": domain},
                timeout=60,
            )

    try:
        response = _request_with_retries(
            submit,
            attempts=attempts,
            retry_delay=retry_delay,
            sleep=sleep,
        )
    except (OSError, requests.RequestException) as error:
        return False, f"上传请求失败：{error}"

    # A concurrent request can briefly observe the claim before task creation.
    for _ in range(attempts - 1):
        if response.status_code != 409:
            break
        sleep(max(0.1, retry_delay))
        try:
            response = submit()
        except (OSError, requests.RequestException) as error:
            return False, f"上传请求失败：{error}"
    if response.status_code not in {200, 202}:
        detail = ""
        try:
            payload = response.json()
            detail = payload.get("detail", "") if isinstance(payload, dict) else ""
        except ValueError:
            pass
        return False, detail or f"上传失败（HTTP {response.status_code}）"

    try:
        payload = response.json()
    except ValueError:
        return False, "上传接口返回了无效 JSON"
    if not isinstance(payload, dict):
        return False, "上传接口返回了无效数据"

    status = str(payload.get("status", "")).lower()
    if status == "duplicate":
        return True, "内容已存在，跳过重复入库"
    if status in TERMINAL_SUCCESS:
        return True, str(payload.get("message") or "入库完成")
    task_id = payload.get("task_id")
    if status != "queued" or not task_id:
        return False, str(payload.get("message") or "上传响应缺少有效任务 ID")

    return wait_for_task(
        session,
        base_url,
        str(task_id),
        poll_interval=poll_interval,
        task_timeout=task_timeout,
        attempts=attempts,
        retry_delay=retry_delay,
        sleep=sleep,
        monotonic=monotonic,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="批量上传 Markdown 文件并等待知识库入库结果"
    )
    parser.add_argument("--directory", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("KNOWLEDGE_API_URL", DEFAULT_BASE_URL),
        help="知识库服务地址；也可通过 KNOWLEDGE_API_URL 设置",
    )
    parser.add_argument(
        "--knowledge-space",
        default="default",
        help="目标知识空间",
    )
    parser.add_argument("--domain", default="general", help="目标知识领域")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--task-timeout", type=float, default=1800.0)
    parser.add_argument("--retry-attempts", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=1.0)
    parser.add_argument("--upload-delay", type=float, default=0.2)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    token = os.environ.get("KNOWLEDGE_SERVICE_TOKEN", "").strip()
    if len(token) < 32:
        print("请设置长度至少为 32 的 KNOWLEDGE_SERVICE_TOKEN。", file=sys.stderr)
        return 2
    if args.retry_attempts < 1 or args.poll_interval <= 0 or args.task_timeout <= 0:
        print("重试次数、轮询间隔和任务超时必须大于 0。", file=sys.stderr)
        return 2
    if args.retry_delay < 0 or args.upload_delay < 0:
        print("重试延迟和上传间隔不能小于 0。", file=sys.stderr)
        return 2
    if not args.directory.is_dir():
        print(f"目录不存在：{args.directory}", file=sys.stderr)
        return 2

    files = sorted(
        path
        for path in args.directory.iterdir()
        if path.is_file() and path.suffix.lower() == ".md"
    )
    print(f"共 {len(files)} 个 Markdown 文件待上传。")
    if not files:
        return 0

    success = 0
    failed = 0
    with requests.Session() as session:
        session.headers.update({"X-Service-Token": token})
        for index, file_path in enumerate(files, start=1):
            ok, message = upload_file(
                session,
                file_path,
                args.base_url,
                knowledge_space=args.knowledge_space,
                domain=args.domain,
                poll_interval=args.poll_interval,
                task_timeout=args.task_timeout,
                attempts=args.retry_attempts,
                retry_delay=args.retry_delay,
            )
            if ok:
                success += 1
                print(f"[{index}/{len(files)}] {file_path.name}：{message}")
            else:
                failed += 1
                print(
                    f"[{index}/{len(files)}] {file_path.name}：{message}",
                    file=sys.stderr,
                )
            if index < len(files) and args.upload_delay:
                time.sleep(args.upload_delay)

    print(f"完成：成功 {success}，失败 {failed}。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
