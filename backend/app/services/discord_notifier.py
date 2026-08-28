"""
디스코드 웹훅 발송 서비스 모듈 (discord_notifier.py).

전달받은 텍스트 메시지를 `.env`의 `DISCORD_WEBHOOK_URL`로 POST한다.
한글 깨짐 방지를 위해 본문을 UTF-8 바이트 배열로 직렬화해 전송한다(CLAUDE.md 5.3).
"""

import json
import logging

import requests

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

# 디스코드 메시지 본문 길이 제한
_DISCORD_CONTENT_LIMIT = 2000


class DiscordNotifier:
    """디스코드 채널 웹훅으로 텍스트 메시지를 발송하는 서비스 클래스."""

    def __init__(self, webhook_url: str = None) -> None:
        """웹훅 URL을 주입합니다(미지정 시 전역 설정값 사용).

        :param webhook_url: 디스코드 Incoming Webhook URL. None이면 settings.DISCORD_WEBHOOK_URL 사용.
        """
        self.webhook_url = (webhook_url if webhook_url is not None else settings.DISCORD_WEBHOOK_URL) or ""

    def send(self, content: str) -> dict:
        """텍스트 메시지를 디스코드 웹훅으로 발송합니다.

        한글 보존을 위해 JSON을 `ensure_ascii=False`로 만든 뒤 **UTF-8 바이트 배열**로 전송한다.
        `requests`가 dict를 직접 직렬화하면 charset이 보장되지 않으므로 바이트로 넘긴다.

        :param content: 전송할 메시지 본문(2000자 초과 시 잘림)
        :return: {"ok": bool, "message": str} — 발송 성공 여부와 사유
        """
        if not self.webhook_url:
            return {"ok": False, "message": "DISCORD_WEBHOOK_URL이 설정되지 않았습니다(.env 확인)."}

        payload = json.dumps(
            {"content": content[:_DISCORD_CONTENT_LIMIT]}, ensure_ascii=False
        ).encode("utf-8")
        try:
            resp = requests.post(
                self.webhook_url,
                data=payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=10,
            )
        except requests.RequestException as exc:
            logger.error("디스코드 전송 실패: %s", exc)
            return {"ok": False, "message": f"디스코드 연결 실패: {exc}"}

        if 200 <= resp.status_code < 300:
            return {"ok": True, "message": "디스코드 전송 완료"}
        logger.error("디스코드 응답 코드 %s: %s", resp.status_code, resp.text[:300])
        return {"ok": False, "message": f"디스코드 응답 코드 {resp.status_code}"}
