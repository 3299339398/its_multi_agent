"""Check indexed content before committing; never print credential values.

Run from anywhere: python its_multi_agent/scripts/check_secrets.py
This checks common token formats and exact local .env secrets, not all possible secrets.
"""
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOKEN = re.compile(rb"(?<![A-Za-z0-9_-])(?:sk-[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{30,}|gh[pousr]_[A-Za-z0-9]{30,})|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def indexed_blobs():
    with subprocess.Popen(["git", "-C", str(ROOT), "cat-file", "--batch"],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE) as process:
        try:
            for entry in git("ls-files", "--stage", "-z").split(b"\0"):
                if not entry or entry.startswith(b"160000 "):
                    continue
                oid = entry.split(b"\t", 1)[0].split()[1]
                process.stdin.write(oid + b"\n")
                process.stdin.flush()
                header = process.stdout.readline().split()
                if len(header) != 3 or header[1] != b"blob":
                    raise RuntimeError("Cannot read indexed blob")
                data = process.stdout.read(int(header[2]))
                process.stdout.read(1)
                yield entry, data
        finally:
            process.stdin.close()
            process.stdout.close()


def main():
    local_secrets = set()
    for path in (ROOT / ".env", ROOT / "its_multi_agent/.env",
                 ROOT / "its_multi_agent/backend/app/.env",
                 ROOT / "its_multi_agent/backend/knowledge/.env"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if line.lstrip().startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            value = value.strip().strip("\"'")
            if re.search(r"KEY|SECRET|TOKEN|PASSWORD|BAIDUMAP_AK", name, re.I) and len(value) >= 12:
                local_secrets.add(value.encode())
    failures = 0
    files = 0
    for entry, data in indexed_blobs():
        meta, raw_path = entry.split(b"\t", 1)
        path = raw_path.decode("utf-8")
        filename = Path(path).name
        if ((filename == ".env" or filename.startswith(".env.")) and not filename.endswith(".example")) or filename.endswith((".key", ".pem", ".p12", ".pfx")):
            print(f"BLOCKED sensitive file: {path}")
            failures += 1
            continue
        files += 1
        if TOKEN.search(data) or any(secret in data for secret in local_secrets):
            print(f"BLOCKED possible credential: {path} (value hidden)")
            failures += 1
    print(f"Checked {files} indexed files; {failures} finding(s). History is not checked by this script.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
