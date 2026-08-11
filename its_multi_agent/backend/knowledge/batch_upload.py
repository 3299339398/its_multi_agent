import os
import requests
import time

crawl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "crawl")
files = [f for f in os.listdir(crawl_dir) if f.endswith(".md")]

total = len(files)
print(f"共 {total} 个文件待上传\n")

success = 0
fail = 0

for i, fname in enumerate(files, 1):
    filepath = os.path.join(crawl_dir, fname)
    try:
        with open(filepath, "rb") as f:
            resp = requests.post("http://127.0.0.1:8001/upload", files={"file": (fname, f)}, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                print(f"[{i}/{total}] {fname} - chunks: {data.get('chunks_added', '?')}")
                success += 1
            else:
                print(f"[{i}/{total}] {fname} - 失败 ({resp.status_code})")
                fail += 1
    except Exception as e:
        print(f"[{i}/{total}] {fname} - 异常: {e}")
        fail += 1

    time.sleep(1)  # 避免压垮服务

print(f"\n完成: 成功 {success}, 失败 {fail}")
