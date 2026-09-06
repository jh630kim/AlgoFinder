"""
수집 커버리지 Discord 리포트 스크립트 (deploy/report_coverage.py).

`roll-lite-db` 워크플로 마지막에 `if: always()` 로 실행된다. 우선 수집기가 남긴
`data/roll_progress.json`(시도/성공 카운트)을 읽어 "성공 개수 / 시도 개수" 를 보고하고,
그 파일이 없으면 `data/app_lite.db` 를 스캔해 "오늘(KST) 수집 종목 수 / 전체" 로 폴백한다.
어떤 경우에도 워크플로를 실패시키지 않는다(exit 0).

메시지 구분(진행파일 기반):
- 완주 + 전량   : ✅ YYYY-MM-DD 수집 N/N
- 완주 + 일부   : ⚠️ YYYY-MM-DD 수집 M/N (누락 K개: 코드… — 다음 실행에서 재시도)
- 타임아웃 중단 : ⚠️ YYYY-MM-DD 수집 중단 M/K 시도 (타임아웃 — 다음 실행 대기)
- 대상 없음     : ℹ️ YYYY-MM-DD 수집 대상 없음 (전 종목 이미 최신)

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
_PROGRESS_FILE = "data/roll_progress.json"


def _dash(ymd: str) -> str:
    """'YYYYMMDD' → 'YYYY-MM-DD'. 형식이 아니면 원문 반환."""
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}" if len(ymd) == 8 and ymd.isdigit() else ymd


def _read_progress() -> dict:
    """`data/roll_progress.json` 을 읽어 dict 로 반환합니다. 없거나 손상 시 None."""
    try:
        with open(_PROGRESS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _message_from_progress(p: dict) -> str:
    """수집기 진행파일로 '성공/시도' 메시지를 만듭니다."""
    att = int(p.get("attempted", 0))
    wd = int(p.get("with_data", 0))
    end = _dash(str(p.get("range", "")).split("~")[-1])
    failed = ", ".join(p.get("failed_sample", [])[:_MISSING_SHOW])
    tail = f" (누락 {att - wd}개: {failed} — 다음 실행에서 재시도)" if att > wd else ""
    if not p.get("done"):
        return f"⚠️ {end} 수집 중단 {wd}/{att} 시도 (타임아웃 — 다음 실행 대기)"
    if att == 0:
        return f"ℹ️ {end} 수집 대상 없음 (전 종목 이미 최신)"
    if wd >= att:
        return f"✅ {end} 수집 {wd}/{att}"
    return f"⚠️ {end} 수집 {wd}/{att}{tail}"


def _message_from_db(db: str) -> str:
    """진행파일이 없을 때: lite DB 를 스캔해 '오늘(KST) 수집/전체' 로 폴백 메시지를 만듭니다."""
    ymd = datetime.now(_KST).strftime("%Y%m%d")
    dash = _dash(ymd)
    if not os.path.exists(db):
        return f"⚠️ {dash} 커버리지 리포트 생성 실패 — {db} 없음 (Actions 로그 확인)"
    try:
        conn = sqlite3.connect(db)
        try:
            q = conn.execute
            total = q("SELECT count(*) FROM target_stocks").fetchone()[0]
            covered = q("SELECT count(DISTINCT symbol) FROM investor_trading_daily "
                        "WHERE date = ?", (ymd,)).fetchone()[0]
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - 리포트 실패가 워크플로를 깨지 않도록
        return f"⚠️ {dash} 커버리지 리포트 생성 실패 — {exc} (Actions 로그 확인)"

    if total and covered >= total:
        return f"✅ {dash} 수집 {covered}/{total}"
    if covered > 0:
        return f"⚠️ {dash} 수집 {covered}/{total} (누락 {total - covered}개 — 다음 실행에서 재시도)"
    return f"ℹ️ {dash} 수집 0/{total} (거래일 아님/휴장 추정)"


def _build_message(db: str) -> str:
    """진행파일 우선, 없으면 DB 스캔으로 Discord 메시지를 만듭니다."""
    prog = _read_progress()
    return _message_from_progress(prog) if prog is not None else _message_from_db(db)


def _post_discord(webhook: str, content: str) -> None:
    """Discord 웹훅으로 메시지를 전송합니다. 실패해도 예외를 전파하지 않습니다."""
    body = json.dumps({"content": content}).encode("utf-8")
    # User-Agent 명시 필수: 기본값(Python-urllib/x.y)은 Discord Cloudflare 가 403 으로 차단한다.
    req = urllib.request.Request(
        webhook, data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "User-Agent": "AlgoFinder/1.0 (roll-lite-db report_coverage)"},
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
