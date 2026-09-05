"""GitHub Actions 워크플로 원격 트리거 서비스 모듈 (workflow_dispatcher.py).

GitHub `schedule` 트리거가 특정 UTC 시간대에서 만성적으로(4~8시간) 지연되므로,
Render 웹 앱이 요청을 처리하는 흐름(UptimeRobot 5분 핑 포함)을 "시계"로 활용해
조건을 만족하면 REST API로 `roll-lite-db` 워크플로를 직접 발동한다.
API 직접 호출(`workflow_dispatch`)은 schedule 큐를 거치지 않아 지연이 없다.

당일 연속 실패가 `_FAIL_LIMIT` 회에 도달하면 Discord로 1회 알림하고 그날은 시도를
멈춘다(다음날 자동 초기화). 발동이 계속 실패해도 수집은 종목별 증분이라 다음 성공
실행에서 빠진 구간이 자동으로 메꿔진다.
"""

import logging
import threading
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# 한국 표준시(KST) 및 발동 대상 워크플로 REST 엔드포인트
_KST = timezone(timedelta(hours=9))
_API_URL = (
    "https://api.github.com/repos/jh630kim/AlgoFinder"
    "/actions/workflows/roll-lite-db.yml/dispatches"
)
_TRIGGER_HOUR_KST = 17  # 이 시각(포함) 이후에만 발동 (OHLCV 종가 안정화 여유)
_FAIL_LIMIT = 12        # 당일 연속 실패가 이 횟수면 알림 + 당일 중단 (≈1시간, 5분 핑 기준)


class WorkflowDispatcher:
    """조건부로 GitHub Actions `roll-lite-db` 워크플로를 원격 발동하는 서비스 클래스."""

    def __init__(self, token: str, webhook_url: str = "") -> None:
        """디스패처를 초기화합니다.

        :param token: GitHub PAT (권한 Actions: Read and write). 빈 문자열이면 항상 비활성.
        :param webhook_url: 실패 임계 도달 시 알림을 보낼 Discord 웹훅 URL. 없으면 알림 생략.
        """
        self._token = token or ""
        self._webhook = webhook_url or ""
        self._lock = threading.Lock()
        self._done_date = ""    # 오늘 발동을 마친(성공 또는 포기) KST 날짜(YYYY-MM-DD)
        self._fail_date = ""    # _fail_count 가 집계 중인 KST 날짜
        self._fail_count = 0    # 당일 연속 실패 횟수
        self._last_err = ""     # 마지막 실패 사유(알림 문구용)
        self._in_flight = False  # 발동 스레드 진행 중 여부(중복 방지)

    def maybe_dispatch(self) -> None:
        """평일 · KST 17시 이후 · 당일 미완료면 백그라운드로 워크플로를 발동합니다.

        요청 처리 흐름을 막지 않도록 실제 HTTP 호출은 별도 스레드에서 수행한다.
        조건 미충족·중복·당일 완료 시 즉시 반환하므로 응답 지연이 없다.
        """
        if not self._token:
            return
        now = datetime.now(_KST)
        if now.weekday() >= 5 or now.hour < _TRIGGER_HOUR_KST:
            return
        today = now.strftime("%Y-%m-%d")
        with self._lock:
            if self._fail_date != today:  # 날짜가 바뀌면 실패 집계 초기화
                self._fail_date, self._fail_count = today, 0
            if self._done_date == today or self._in_flight:
                return
            self._in_flight = True
        threading.Thread(target=self._dispatch, args=(today,),
                         name="wf-dispatch", daemon=True).start()

    def _dispatch(self, today: str) -> None:
        """실제 GitHub API 호출. 성공 시 당일 완료 처리, 실패 시 카운트 증가·임계 도달 시 알림.

        :param today: 발동 대상 KST 날짜(YYYY-MM-DD).
        """
        import requests  # 웹 프로필 전용 의존성 — 지연 import

        ok, err = False, ""
        try:
            res = requests.post(
                _API_URL,
                headers={"Authorization": f"Bearer {self._token}",
                         "Accept": "application/vnd.github+json"},
                json={"ref": "master"}, timeout=10,
            )
            ok = 200 <= res.status_code < 300
            err = "" if ok else f"HTTP {res.status_code} {res.text[:150]}"
        except Exception as exc:  # noqa: BLE001 - 트리거 실패는 웹 서비스에 영향 없음
            err = f"{type(exc).__name__}: {exc}"
        self._finish(today, ok, err)

    def _finish(self, today: str, ok: bool, err: str) -> None:
        """발동 결과를 반영합니다. 성공=당일 완료, 실패=카운트++·임계 도달 시 알림+중단."""
        alert = None
        with self._lock:
            self._in_flight = False
            if ok:
                self._done_date = today
                logger.info(f"[wf-dispatch] roll-lite-db 발동 성공 ({today})")
                return
            self._fail_count += 1
            self._last_err = err
            logger.warning(f"[wf-dispatch] 발동 실패 {self._fail_count}회: {err}")
            if self._fail_count >= _FAIL_LIMIT:
                self._done_date = today  # 당일 재시도 중단
                alert = (f"⚠️ roll-lite-db 원격 발동 {self._fail_count}회 실패 ({today}) "
                         f"— 마지막 오류 {err}. 토큰/권한 확인 필요. 당일 재시도 중단.")
        if alert:
            self._send_alert(alert)

    def _send_alert(self, content: str) -> None:
        """Discord 웹훅으로 실패 알림을 전송합니다. 실패해도 예외를 전파하지 않습니다."""
        if not self._webhook:
            logger.warning(f"[wf-dispatch] (웹훅 미설정) {content}")
            return
        import requests

        try:
            requests.post(self._webhook, json={"content": content}, timeout=10)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[wf-dispatch] 실패 알림 전송 예외: {exc}")
