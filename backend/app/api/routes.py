"""
Flask RESTful API 라우트 모듈 (routes.py).

대시보드 차트, 수급 TOP 20, 증분 수집, 구분/업종 연쇄 필터링 파이프라인 API 엔드포인트를 제공합니다.
"""

from flask import Blueprint, request, jsonify
from backend.app.core.database import db_manager
from backend.app.repositories.web_repository import WebRepository

api_bp = Blueprint("api", __name__, url_prefix="/api")

sync_status = {
    "is_running": False,
    "progress": 0.0,
    "last_sync": "-",
    "message": "대기 중"
}


@api_bp.route("/search-stock", methods=["GET"])
def search_stock():
    """종목코드 및 종목명 자동완성 검색 API."""
    query_str = request.args.get("q", "").strip()
    session = next(db_manager.get_session())
    try:
        repo = WebRepository(session)
        result = repo.search_stocks(query_str)
        return jsonify({"status": "success", "data": result})
    finally:
        session.close()


@api_bp.route("/target-categories", methods=["GET"])
def target_categories():
    """target_stocks 구분 카테고리 목록 반환 API."""
    session = next(db_manager.get_session())
    try:
        repo = WebRepository(session)
        categories = repo.get_target_categories()
        return jsonify({"status": "success", "data": categories})
    finally:
        session.close()


@api_bp.route("/target-industries", methods=["GET"])
def target_industries():
    """선택된 구분에 속한 target_stocks 세부 업종(industry) 목록 반환 API."""
    category = request.args.get("category", "ALL").strip()
    session = next(db_manager.get_session())
    try:
        repo = WebRepository(session)
        industries = repo.get_target_industries(category=category)
        return jsonify({"status": "success", "category": category, "data": industries})
    finally:
        session.close()


@api_bp.route("/filtered-stocks", methods=["GET"])
def filtered_stocks():
    """구분 및 업종 조건으로 수급 데이터가 수집된 유일 종목 리스트 및 개수 반환 API."""
    category = request.args.get("category", "ALL").strip()
    industry = request.args.get("industry", "ALL").strip()
    session = next(db_manager.get_session())
    try:
        repo = WebRepository(session)
        stocks = repo.get_filtered_target_stocks(category=category, industry=industry)
        return jsonify({
            "status": "success",
            "category": category,
            "industry": industry,
            "total_count": len(stocks),
            "data": stocks
        })
    finally:
        session.close()


@api_bp.route("/aggregate-chart", methods=["GET"])
def aggregate_chart():
    """구분 및 업종 전체 종목의 날짜별 평균 주가 및 수급 집계 데이터 반환 API."""
    category = request.args.get("category", "ALL").strip()
    industry = request.args.get("industry", "ALL").strip()
    limit = int(request.args.get("limit", 120))
    session = next(db_manager.get_session())
    try:
        repo = WebRepository(session)
        data = repo.get_aggregate_chart_data(category=category, industry=industry, limit=limit)
        return jsonify({
            "status": "success",
            "category": category,
            "industry": industry,
            "data": data
        })
    finally:
        session.close()


@api_bp.route("/stock-chart/<stock_code>", methods=["GET"])
def stock_chart(stock_code: str):
    """해당 종목의 OHLCV + 4대 수급 데이터 JSON 반환 API."""
    limit = int(request.args.get("limit", 120))
    session = next(db_manager.get_session())
    try:
        repo = WebRepository(session)
        data = repo.get_stock_chart_data(stock_code, limit=limit)
        return jsonify({"status": "success", "stock_code": stock_code, "data": data})
    finally:
        session.close()


@api_bp.route("/top-investor-trading", methods=["GET"])
def top_investor_trading():
    """외국인/기관/연기금 순매수 상위 TOP 20 종목 조회 API."""
    target_date = request.args.get("date", "").strip()
    session = next(db_manager.get_session())
    try:
        repo = WebRepository(session)
        data = repo.get_top_investor_trading(target_date=target_date)
        return jsonify({"status": "success", "data": data})
    finally:
        session.close()


@api_bp.route("/market-indices", methods=["GET"])
def market_indices():
    """헤더 요약 칩 3종 데이터 및 주요 지수 조회 API."""
    session = next(db_manager.get_session())
    try:
        repo = WebRepository(session)
        summary = repo.get_market_indices_summary()
        summary["sync_status"] = sync_status
        return jsonify({"status": "success", "data": summary})
    finally:
        session.close()
