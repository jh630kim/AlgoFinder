"""
수집 커버리지 Discord 리포트 스크립트 (deploy/report_coverage.py).

`roll-lite-db` 워크플로 마지막에 `if: always()` 로 실행된다. 갱신된
`data/app_lite.db` 에서 "오늘(KST) 날짜에 데이터가 들어온 타깃 종목 수 / 전체 타깃 수"
를 계산해 Discord 웹훅으로 1회 보고한다. 어떤 경우에도 워크플로를 실패시키지 않는다(exit 0).

메시지 구분:
- 전량 수집        : ✅ YYYY-MM-DD 수집 N/N
- 일부 누락        : ⚠️ YYYY-MM-DD 수집 M/N (누락 K개: 코드… — 다음 실행에서 재시도)
- 0건(휴장/오류)   : ℹ️ YYYY-MM-DD 수집 0/N (거래일 아님/휴장 추정)
- DB 조회 실패     : ⚠️ YYYY-MM-DD 커버리지 리포트 생성 실패 — Actions 로그 확인

환경변수:
    DISCORD_WEBHOOK_URL   미설정 시 표준출력에만 남기고 종료
사용법:
    python deploy/report_coverage.py [--db data/app_lite.db]
"""

import argparse
import json
import os
import sqlite3
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

# 콘솔 인코딩 방어: 로컬 Windows(cp949) 에서 이모지 print 시 UnicodeEncodeError 로 죽지 않게.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

_KST = timezone(timedelta(hours=9))
_MISSING_SHOW = 10  # 메시지에 함께 표기할 누락 종목 코드 최대 개수


def _kst_today() -> str:
    """현재 KST 날짜를 'YYYYMMDD'(DB 저장 포맷)로 반환합니다."""
    return datetime.now(_KST).strftime("%Y%m%d")


def _coverage(db: str, ymd: str) -> tuple:
    """(수집 종목 수, 전체 타깃 수, 누락 종목 코드 리스트)를 반환합니다."""
    conn = sqlite3.connect(db)
    try:
        q = conn.execute
        total = q("SELECT count(*) FROM target_stocks").fetchone()[0]
        covered = q(
            "SELECT count(DISTINCT symbol) FROM investor_trading_daily WHERE date = ?",
            (ymd,),
        ).fetchone()[0]
        missing = [
            r[0] for r in q(
                "SELECT symbol FROM target_stocks WHERE symbol NOT IN "
                "(SELECT symbol FROM investor_trading_daily WHERE date = ?) "
                "ORDER BY symbol LIMIT ?",
                (ymd, _MISSING_SHOW),
            )
        ]
        return covered, total, missing
    finally:
        conn.close()


def _build_message(db: str) -> str:
    """커버리지를 계산해 Discord 로 보낼 한 줄 메시지를 만듭니다."""
    ymd = _kst_today()
    dash = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"
    if not os.path.exists(db):
        return f"⚠️ {dash} 커버리지 리포트 생성 실패 — {db} 없음 (Actions 로그 확인)"
    try:
        covered, total, missing = _coverage(db, ymd)
    except Exception as exc:  # noqa: BLE001 - 리포트 실패가 워크플로를 깨지 않도록
        return f"⚠️ {dash} 커버리지 리포트 생성 실패 — {exc} (Actions 로그 확인)"

    if total and covered >= total:
        return f"✅ {dash} 수집 {covered}/{total}"
    if covered > 0:
        codes = ", ".join(missing)
        more = " …" if (total - covered) > len(missing) else ""
        return (f"⚠️ {dash} 수집 {covered}/{total} "
                f"(누락 {total - covered}개: {codes}{more} — 다음 실행에서 재시도)")
    return f"ℹ️ {dash} 수집 0/{total} (거래일 아님/휴장 추정)"


def _post_discord(webhook: str, content: str) -> None:
    """Discord 웹훅으로 메시지를 전송합니다. 실패해도 예외를 전파하지 않습니다."""
    body = json.dumps({"content": content}).encode("utf-8")
    req = urllib.request.Request(
        webhook, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            print(f"[report_coverage] Discord 전송 HTTP {res.status}")
    except Exception as exc:  # noqa: BLE001 - 전송 실패는 로그만
        print(f"[report_coverage] Discord 전송 실패: {exc}")


def main() -> None:
    """커버리지 메시지를 만들어 출력하고, 웹훅이 있으면 Discord 로 보냅니다."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/app_lite.db")
    args = ap.parse_args()

    message = _build_message(args.db)
    print(message)
    webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if webhook:
        _post_discord(webhook, message)
    else:
        print("[report_coverage] DISCORD_WEBHOOK_URL 미설정 — 전송 생략")


if __name__ == "__main__":
    main()
