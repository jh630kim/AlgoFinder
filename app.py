"""
AlgoFinder Flask 웹 백엔드 메인 애플리케이션 (app.py).

4대 대시보드 페이지 라우팅 및 RESTful API 블루프린트를 등록하고 서버를 구동합니다.
- / : 메인 대시보드
- /backtest : 시뮬레이션
- /recommendation : 모의투자
- /proposal : 투자제안 (PC/모바일 자동 감지 및 분기)
- /proposal-mobile : 투자제안 모바일 TEST 전용
"""

import os
import sys
import threading
from flask import Flask, render_template, request, redirect, url_for, jsonify
from dotenv import load_dotenv

# 콘솔 인코딩 방어: 로그 리다이렉트/서비스 실행 환경에서 표준 출력이 cp949로
# 잡히면 이모지·한글 print 시 UnicodeEncodeError로 프로세스가 죽는다.
# Python 3.7+ 스트림 재설정으로 UTF-8 고정하고, 실패해도 기동은 계속한다.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def safe_print(message: str) -> None:
    """표준 출력 인코딩이 문자를 표현하지 못해도 예외 없이 출력한다."""
    try:
        print(message)
    except UnicodeEncodeError:
        enc = (getattr(sys.stdout, "encoding", None) or "ascii")
        print(message.encode(enc, errors="replace").decode(enc, errors="replace"))


# .env 환경 변수 로드
load_dotenv()

from backend.app.core.config import settings
from backend.app.core.database import db_manager
from backend.app.api import api_bp, paper_api_bp
from backend.app.repositories.web_repository import WebRepository
from backend.app.repositories.market_indices_repository import MarketIndicesRepository

# 실행 프로필 / 읽기 전용 모드
WEB_PROFILE = settings.APP_PROFILE.lower() == "web"   # web: 투자제안 모바일만 노출
READONLY = bool(settings.READONLY)                     # True: 시세 동기화(쓰기)만 차단

# Flask 앱 생성 및 템플릿/스태틱 디렉토리 설정
app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)

# 데이터베이스 테이블 자동 생성 보장
db_manager.create_all_tables()

# API 블루프린트 등록
app.register_blueprint(api_bp)
app.register_blueprint(paper_api_bp)


def _warm_proposal_cache() -> None:
    """배포/기동 직후 첫 방문자가 전체 워밍업 비용을 페이지 로드 중에 부담하지 않도록,
    최신 거래일 기준 투자제안(advice) 추천 캐시를 백그라운드 스레드에서 미리 채운다.

    ProposalAdvisorCache 는 프로세스 전역 캐시이므로, 이 예열이 끝나면 이후 같은
    거래일에 대한 /api/recommended-stocks 요청은 재로딩 없이 창 슬라이스만 수행한다.
    데이터가 없거나 예열이 실패해도 서비스 기동에는 영향을 주지 않는다(로그만 남김).
    """
    try:
        from backend.app.services.proposal_advisor_cache import ProposalAdvisorCache

        session = next(db_manager.get_session())
        try:
            latest = ProposalAdvisorCache.data_version(session)
            if not latest:
                return
            advisor = ProposalAdvisorCache.get(session, latest, "advice")
            # 추천 표와 순수관행 합성 랭킹까지 조립해 실제 요청 경로와 동일하게 예열한다.
            advisor.get_recommendations(latest)
            advisor.get_composite_top(latest, n=10)
        finally:
            session.close()
        safe_print(f"[warm] 투자제안 추천 캐시 예열 완료 (기준일 {latest})")
    except Exception as exc:  # 예열 실패는 무시하고 기동을 계속한다
        safe_print(f"[warm] 추천 캐시 예열 실패(무시): {exc}")


# 개발 리로더의 부모 프로세스에서 중복 실행하지 않도록, 디버그 모드에서는
# 실제 서빙 자식 프로세스(WERKZEUG_RUN_MAIN=true)에서만 예열한다.
# gunicorn(FLASK_DEBUG=False)에서는 워커 import 시 1회 실행된다.
_DEBUG_MODE = os.getenv("FLASK_DEBUG", "True").lower() == "true"
if (not _DEBUG_MODE) or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    threading.Thread(target=_warm_proposal_cache, name="warm-proposal", daemon=True).start()

# web 프로필: PC 전용 페이지는 투자제안 모바일로 리다이렉트
_WEB_REDIRECT_PAGES = {"/", "/backtest", "/recommendation", "/proposal"}
# READONLY: 시세 쓰기 경로만 차단(가상매매 paper 쓰기는 영향 없음)
_READONLY_BLOCKED_PREFIXES = ("/api/sync",)

# GitHub `schedule` 트리거 지연 우회: 웹 프로필에서만, 요청 흐름을 시계 삼아
# 평일 KST 17시 이후 하루 1회 roll-lite-db 워크플로를 원격 발동한다(비차단).
from backend.app.services.workflow_dispatcher import WorkflowDispatcher
_wf_dispatcher = WorkflowDispatcher(settings.GITHUB_DISPATCH_TOKEN, settings.DISCORD_WEBHOOK_URL)


@app.before_request
def _profile_readonly_gate():
    """실행 프로필·읽기전용 규칙에 따라 요청을 사전 차단/리다이렉트합니다.

    아울러 web 프로필에서는 매 요청을 계기로 데이터 갱신 워크플로 원격 발동을 시도한다
    (조건 미충족·중복 시 즉시 무시하므로 응답 지연 없음).
    """
    if WEB_PROFILE:
        _wf_dispatcher.maybe_dispatch()
    path = "/" + request.path.strip("/")
    if WEB_PROFILE and path in _WEB_REDIRECT_PAGES:
        return redirect(url_for("proposal_mobile"))
    if READONLY and path.startswith(_READONLY_BLOCKED_PREFIXES):
        return jsonify({"status": "error", "message": "읽기 전용 모드입니다(시세 동기화 비활성)."}), 403
    return None


def _latest_trading_date() -> str:
    """수급 일별 데이터의 최신 거래일자를 'YYYY-MM-DD' 형식으로 반환합니다.

    메인 대시보드 상단 '📅 최근 거래일' 칩과 동일한 소스
    (WebRepository.get_market_indices_summary()의 latest_date)를 재사용하여,
    투자제안 화면의 추천 기준일 기본값 및 '최근 수집일' 표시를 서버 렌더 시점에
    채우기 위한 헬퍼입니다.

    :returns: 최신 거래일 문자열('YYYY-MM-DD'). 데이터가 없으면 빈 문자열('').
    """
    session = next(db_manager.get_session())
    try:
        raw = WebRepository(session).get_market_indices_summary().get("latest_date", "")
    finally:
        session.close()

    # DB 저장 포맷은 'YYYYMMDD' → date input이 요구하는 'YYYY-MM-DD'로 변환
    if raw and raw.isdigit() and len(raw) == 8:
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    # 이미 'YYYY-MM-DD'면 그대로, 데이터 없음('-'/'') 이면 빈 문자열
    if raw and "-" in raw:
        return raw
    return ""


def _kospi_regime_ssr() -> dict:
    """최신 거래일 기준 코스피 20일선 방향(장세) 판정 결과를 서버 렌더용으로 반환합니다.

    투자제안 화면 '📊 코스피 20일선' 배지의 초기값을 첫 HTML 응답에 포함해
    JS 조회 완료 전 깜빡임을 방지하기 위한 헬퍼입니다.

    :returns: KospiRegimeAnalyzer.analyze() 결과 dict (실패 시 available=False 형태)
    """
    from backend.app.services.kospi_regime_analyzer import KospiRegimeAnalyzer
    session = next(db_manager.get_session())
    try:
        latest = MarketIndicesRepository(session).get_max_date() or ""
        return KospiRegimeAnalyzer(session).analyze(latest)
    finally:
        session.close()


def is_mobile_user_agent(user_agent_str: str) -> bool:
    """요청의 User-Agent 헤더를 검사하여 모바일 기기 접속 여부를 판별합니다."""
    if not user_agent_str:
        return False
    ua = user_agent_str.lower()
    mobile_keywords = ["android", "iphone", "ipad", "ipod", "blackberry", "windows phone", "mobile"]
    return any(keyword in ua for keyword in mobile_keywords)


@app.route("/")
def index():
    """메인 대시보드 페이지 라우트."""
    return render_template("index.html", readonly=READONLY)


@app.route("/backtest")
def backtest():
    """시뮬레이션 분석실 페이지 라우트."""
    return render_template("backtest.html")


@app.route("/recommendation")
def recommendation():
    """모의투자 분석실 페이지 라우트.

    투자제안 화면과 동일하게 기준일 기본값·최근 수집일·코스피 20일선 국면을 SSR로 주입합니다.
    """
    return render_template(
        "recommendation.html",
        latest_trading_date=_latest_trading_date(),
        kospi_regime=_kospi_regime_ssr(),
    )


@app.route("/proposal")
def proposal():
    """
    투자제안 분석실 페이지 라우트.
    모바일 기기 접속을 자동 감지하여 모바일 전용 뷰(/proposal-mobile)로 자동 리다이렉트합니다.
    """
    user_agent = request.headers.get("User-Agent", "")
    if is_mobile_user_agent(user_agent):
        return redirect(url_for("proposal_mobile"))
    return render_template(
        "proposal.html",
        latest_trading_date=_latest_trading_date(),
        kospi_regime=_kospi_regime_ssr(),
        turso_sync=_turso_sync_enabled(),
    )


@app.route("/proposal-mobile")
def proposal_mobile():
    """투자제안 모바일 TEST 전용 페이지 라우트."""
    return render_template(
        "proposal_mobile.html",
        latest_trading_date=_latest_trading_date(),
        kospi_regime=_kospi_regime_ssr(),
        turso_sync=_turso_sync_enabled(),
    )


def _turso_sync_enabled() -> bool:
    """로컬(full 프로필)에서 PAPER_DATABASE_URL 이 설정돼 있으면 Turso 동기화 버튼을 노출한다.

    web 프로필은 앱이 이미 Turso를 직접 보므로 동기화가 무의미해 숨긴다.
    """
    return (not WEB_PROFILE) and bool(settings.PAPER_DATABASE_URL)


if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    safe_print(f"🚀 AlgoFinder 웹 서버가 http://{host}:{port} 에서 기동됩니다.")
    app.run(host=host, port=port, debug=debug)
