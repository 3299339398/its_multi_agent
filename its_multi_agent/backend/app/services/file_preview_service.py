"""短期预览凭证；HTML 始终在不拥有应用 origin 的 sandbox 中执行。"""
import base64
import hashlib
import hmac
import json
import time

from its_multi_agent.backend.app.config.settings import settings


def _secret():
    if not settings.AUTH_JWT_SECRET or len(settings.AUTH_JWT_SECRET) < 32:
        raise ValueError("预览签名密钥未配置")
    return settings.AUTH_JWT_SECRET.encode()


def issue_preview_ticket(user_id, artifact_id):
    payload = base64.urlsafe_b64encode(json.dumps(
        [user_id, artifact_id, int(time.time()) + 300], separators=(",", ":"),
    ).encode()).decode().rstrip("=")
    signature = hmac.new(_secret(), b"file-preview\0" + payload.encode(), hashlib.sha256).hexdigest()
    return payload + "." + signature


def verify_preview_ticket(ticket):
    try:
        payload, signature = ticket.split(".")
        expected = hmac.new(_secret(), b"file-preview\0" + payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("预览凭证无效")
        user_id, artifact_id, expires_at = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if expires_at <= time.time():
            raise ValueError("预览已过期，请重新打开")
        return user_id, artifact_id
    except (ValueError, TypeError, UnicodeError) as error:
        raise ValueError("预览凭证无效或已过期") from error
