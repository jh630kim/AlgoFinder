"""GitHub Actions 워크플로 원격 트리거 서비스 모듈 (workflow_dispatcher.py).

GitHub `schedule` 트리거가 특정 UTC 시간대에서 만성적으로(4~8시간) 지연되므로,
Render 웹 앱이 요청을 처리하는 흐름(UptimeRobot 5분 핑 포함)을 "시계"로 활용해
조건을 만족하면 REST API로 `roll-lite-db` 워크플로를 직접 발동한다.
API 직접 호출(`workflow_dispatch`)은 schedule 큐를 거치지 않아 지연이 없다.

당일 연속 실패가 `_FAIL_LIMIT` 회에 도달하면 Discord로 1회 알림하고 그날은 시도를
멈춘다(다음날 자동 초기화). 발동이 계속 실패해도 수집은 종목별 증분이라 다음 성공
실행에서 빠진 구간이 자동으로 메꿔진다.

발동 성공 시 워크플로 마지막 단계가 이 웹 앱을 재배포하는데, Render는 매번 Docker
이미지를 새로 빌드하며 그 시점에 경량 DB를 Release 자산에서 다시 받아오므로, 컨테이너
재시작으로 `_done_date`(프로세스 메모리) 가 초기화된다. 그대로면 재배포 직후 첫 요청이
당일 조건을 다시 만족해 같은 날 두 번째로 발동해버린다(두 번째는 이미 최신이라
"수집대상 없음"으로 끝남). `is_data_fresh` 콜백으로 로컬 DB에 오늘자 데이터가 이미
반영돼 있는지 먼저 확인해, 재배포로 초기화된 상태라도 불필요한 재발동을 막는다.
"""

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

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

    def __init__(self, token: str, webhook_url: str = "",
                 is_data_fresh: Optional[Callable[[], bool]] = None) -> None:
        """디스패처를 초기화합니다.

        :param token: GitHub PAT (권한 Actions: Read and write). 빈 문자열이면 항상 비활성.
        :param webhook_url: 실패 임계 도달 시 알림을 보낼 Discord 웹훅 URL. 없으면 알림 생략.
        :param is_data_fresh: 로컬 DB에 오늘자 데이터가 이미 반영됐는지 판단하는 콜백.
            True를 반환하면 발동을 건너뛴다(재배포로 상태가 초기화된 경우의 중복 발동 방지).
            None이면 이 판단을 생략하고 기존 당일 1회 가드만 사용한다.
        """
        self._token = token or ""
        self._webhook = webhook_url or ""
        self._is_data_fresh = is_data_fresh
        self._lock = threading.Lock()
        self._done_date = ""    # 오늘 발동을 마친(성공 또는 포기) KST 날짜(YYYY-MM-DD)
        self._fail_date = ""    # _fail_count 가 집계 중인 KST 날짜
        self._fail_count = 0    # 당일 연속 실패 횟수
        self._last_err = ""     # 마지막 실패 사유(알림 문구용)
        self._in_flight = False  # 발동 스레드 진행 중 여부(중복 방지)
        self._weekend_notice_date = ""  # 주말 휴장 안내를 이미 보낸 KST 날짜(YYYY-MM-DD)

    def maybe_dispatch(self) -> None:
        """평일 · KST 17시 이후 · 당일 미완료면 백그라운드로 워크플로를 발동합니다.

        요청 처리 흐름을 막지 않도록 실제 HTTP 호출은 별도 스레드에서 수행한다.
        조건 미충족·중복·당일 완료·로컬 데이터 이미 최신 시 즉시 반환하므로 응답 지연이 없다.
        주말은 애초에 휴장이라 발동을 시도하지 않되, 같은 시각(17시)에 휴장 안내만 1회 보낸다.
        """
        if not self._token:
            return
        now = datetime.now(_KST)
        if now.weekday() >= 5:
            self._maybe_notify_weekend(now)
            return
        if now.hour < _TRIGGER_HOUR_KST:
            return
        today = now.strftime("%Y-%m-%d")
        with self._lock:
            if self._fail_date != today:  # 날짜가 바뀌면 실패 집계 초기화
                self._fail_date, self._fail_count = today, 0
            if (self._done_date != today and not self._in_flight
                    and self._is_data_fresh and self._is_data_fresh()):
                # 재배포로 프로세스가 재시작돼 _done_date 가 초기화됐어도, 로컬 DB에
                # 이미 오늘자 데이터가 있으면 실제로는 할 일이 없는 것이므로 완료 처리한다.
                self._done_date = today
                logger.info(f"[wf-dispatch] 로컬 데이터 이미 최신 — 발동 생략 ({today})")
            if self._done_date == today or self._in_flight:
                return
            self._in_flight = True
        threading.Thread(target=self._dispatch, args=(today,),
                         name="wf-dispatch", daemon=True).start()

    def _maybe_notify_weekend(self, now: datetime) -> None:
        """주말(휴장)엔 발동을 시도하지 않는다는 사실을 KST 17시부터 하루 1회만 알린다."""
        if now.hour < _TRIGGER_HOUR_KST:
            return
        today = now.strftime("%Y-%m-%d")
        with self._lock:
            if self._weekend_notice_date == today:
                return
            self._weekend_notice_date = today
        label = "토요일" if now.weekday() == 5 else "일요일"
        self._send_alert(f"ℹ️ {today} {label}은 휴장이라 수집 발동을 건너뜁니다.")

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
        """Discord 웹훅으로 알림(실패·주말 안내 등)을 전송합니다. 실패해도 예외를 전파하지 않습니다."""
        if not self._webhook:
            logger.warning(f"[wf-dispatch] (웹훅 미설정) {content}")
            return
        import requests

        try:
            # User-Agent 명시: 기본값(python-requests/x.y)이 Discord 에서 간헐 403 차단됨.
            requests.post(
                self._webhook, json={"content": content}, timeout=10,
                headers={"User-Agent": "AlgoFinder/1.0 (wf-dispatch)"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[wf-dispatch] 실패 알림 전송 예외: {exc}")
