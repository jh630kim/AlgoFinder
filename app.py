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
from flask import Flask, render_template, request, redirect, url_for
from dotenv import load_dotenv

# .env 환경 변수 로드
load_dotenv()

from backend.app.core.database import db_manager
from backend.app.api import api_bp, paper_api_bp

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
    return render_template("index.html")


@app.route("/backtest")
def backtest():
    """시뮬레이션 분석실 페이지 라우트."""
    return render_template("backtest.html")


@app.route("/recommendation")
def recommendation():
    """모의투자 분석실 페이지 라우트."""
    return render_template("recommendation.html")


@app.route("/proposal")
def proposal():
    """
    투자제안 분석실 페이지 라우트.
    모바일 기기 접속을 자동 감지하여 모바일 전용 뷰(/proposal-mobile)로 자동 리다이렉트합니다.
    """
    user_agent = request.headers.get("User-Agent", "")
    if is_mobile_user_agent(user_agent):
        return redirect(url_for("proposal_mobile"))
    return render_template("proposal.html")


@app.route("/proposal-mobile")
def proposal_mobile():
    """투자제안 모바일 TEST 전용 페이지 라우트."""
    return render_template("proposal_mobile.html")


if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    print(f"🚀 AlgoFinder 웹 서버가 http://{host}:{port} 에서 기동됩니다.")
    app.run(host=host, port=port, debug=debug)
