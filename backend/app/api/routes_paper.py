"""
모의투자(account_type='rec') 및 투자제안(account_type='prop') 분리 API 라우트 모듈 (routes_paper.py).

계좌유형별 독립 자산 관리(reset, buy, sell, manual-buy) 및 백테스트 리더보드 API를 담당합니다.
"""

import os
import json
import tempfile
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from backend.app.core.database import db_manager
from backend.app.repositories.paper_trading_repository import PaperTradingRepository
from backend.app.models.all_stock_master import AllStockMaster

logger = logging.getLogger(__name__)
paper_api_bp = Blueprint("paper_api", __name__, url_prefix="/api")

BACKTEST_PROGRESS = {
    "status": "idle",
    "completed": 0,
    "total": 8,
    "message": ""
}

# 렌더 payload(리더보드/차트/매매일지) 파일 캐시: backtest_run 완료 시 1회 기록, 조회 시 재사용
RENDER_CACHE_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "backtest_render_cache.json")
)


def _read_render_cache():
    """렌더 payload 캐시 파일을 읽어 dict로 반환합니다. 없거나 손상 시 None."""
    try:
        with open(RENDER_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _write_render_cache(payload):
    """렌더 payload를 임시 파일에 쓴 뒤 원자적으로 교체 저장합니다(읽기 경합 방지)."""
    try:
        os.makedirs(os.path.dirname(RENDER_CACHE_FILE), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(RENDER_CACHE_FILE), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, RENDER_CACHE_FILE)
    except OSError as e:
        logger.error(f"렌더 캐시 저장 실패: {e}")

@paper_api_bp.route("/backtest-progress", methods=["GET"])
def backtest_progress():
    """백테스트 시뮬레이션 진행 상황을 반환합니다."""
    return jsonify(BACKTEST_PROGRESS)

@paper_api_bp.route("/backtest-run", methods=["POST"])
def backtest_run():
    """프론트엔드 수동 트리거로 백테스트 엔진을 강제 구동합니다."""
    if BACKTEST_PROGRESS.get("status") == "running":
        return jsonify({"status": "error", "message": "이미 백테스트 연산이 진행 중입니다. 잠시 후 다시 시도해 주세요."})

    data = request.get_json() or {}
    period = data.get("period", "3y").strip()
    custom_start = data.get("start_date", "").strip()
    custom_end = data.get("end_date", "").strip()

    BACKTEST_PROGRESS["status"] = "running"
    BACKTEST_PROGRESS["completed"] = 0
    BACKTEST_PROGRESS["message"] = f"{period} 기간 백테스트 준비 중..."

    session = next(db_manager.get_session())
    try:
        from backend.app.services.backtest_engine import BacktestEngine
        from backend.app.models.market_indices_daily import MarketIndicesDaily
        from backend.app.repositories.strategy_leaderboard_repository import StrategyLeaderboardRepository
        from backend.app.repositories.strategy_trade_logs_repository import StrategyTradeLogsRepository
        from backend.app.repositories.strategy_daily_equity_repository import StrategyDailyEquityRepository

        records = session.query(MarketIndicesDaily.date).order_by(MarketIndicesDaily.date.asc()).all()
        dates = [r.date.replace("-", "") for r in records if r.date]
        if not dates:
            BACKTEST_PROGRESS["status"] = "error"
            return jsonify({"status": "error", "message": "시장 지수 데이터가 없습니다."})

        if period == "custom" and custom_start and custom_end:
            start_date = custom_start.replace("-", "")
            end_date = custom_end.replace("-", "")
        else:
            period_limits = {"6m": 125, "1y": 250, "3y": 750, "5y": 1250, "all": 5000}
            limit = period_limits.get(period, 750)
            target_dates = dates[-limit:] if len(dates) >= limit else dates
            start_date = target_dates[0]
            end_date = target_dates[-1]

        # 백테스트 결과 3개 테이블 전체 초기화 후 단일 전략 8종(combo_id 1~8)만 재연산
        StrategyLeaderboardRepository(session).clear_all()
        StrategyTradeLogsRepository(session).clear_all()
        StrategyDailyEquityRepository(session).clear_all()

        engine = BacktestEngine(session)
        for c_id in range(1, 9):
            try:
                engine.run_backtest_for_combo(
                    combo_id=c_id,
                    initial_capital=10000000.0,
                    max_slots=3,
                    start_date=start_date,
                    end_date=end_date,
                    target_sectors=["KOSPI 200", "KOSDAQ 150"]
                )
            except Exception as e:
                logger.error(f"Combo {c_id} 오류: {e}")
            BACKTEST_PROGRESS["completed"] = c_id
            BACKTEST_PROGRESS["message"] = f"전략 조합 {c_id}/8 연산 완료..."

        # 렌더 payload를 1회 조립해 파일 캐시에 저장 (이후 조회는 재조립 없이 반환)
        from backend.app.services.backtest_leaderboard_builder import BacktestLeaderboardBuilder
        payload = BacktestLeaderboardBuilder(session).build(period, custom_start, custom_end, True)
        _write_render_cache(payload)

        BACKTEST_PROGRESS["status"] = "completed"
        BACKTEST_PROGRESS["message"] = "백테스트 완료"
        return jsonify({"status": "success", "message": "백테스트가 성공적으로 완료되었습니다."})
    except Exception as e:
        BACKTEST_PROGRESS["status"] = "error"
        BACKTEST_PROGRESS["message"] = f"오류 발생: {str(e)}"
        return jsonify({"status": "error", "message": str(e)})
    finally:
        session.close()


def _ymd(raw: str) -> str:
    """'YYYY-MM-DD' 또는 'YYYYMMDD' 문자열을 'YYYYMMDD'로 정규화합니다(빈 값이면 오늘)."""
    s = (raw or "").strip().replace("-", "")
    return s if len(s) == 8 and s.isdigit() else datetime.now().strftime("%Y%m%d")


@paper_api_bp.route("/recommended-stocks", methods=["GET"])
def recommended_stocks():
    """기준일 종가(D-0) 기준 S1~S5(8전략) 전략별 TOP 3 매수 추천 종목 반환 API."""
    target_date = _ymd(request.args.get("target_date") or request.args.get("date"))
    session = next(db_manager.get_session())
    try:
        from backend.app.services.proposal_advisor_cache import ProposalAdvisorCache
        result = ProposalAdvisorCache.get(session, target_date).get_recommendations(target_date)
        return jsonify({"status": "success", **result})
    finally:
        session.close()


@paper_api_bp.route("/paper-trading/stock-info", methods=["GET"])
def stock_info():
    """종목코드로 종목명·시장·기준일 종가를 조회합니다(수동 매수 모달 자동 채움용)."""
    code = request.args.get("code", "").strip()
    target_date = _ymd(request.args.get("target_date"))
    if not code:
        return jsonify({"status": "error", "message": "종목코드를 입력해 주세요."}), 400

    session = next(db_manager.get_session())
    try:
        from backend.app.models.investor_trading_daily import InvestorTradingDaily
        master = session.query(AllStockMaster).filter(AllStockMaster.code == code).first()
        row = (
            session.query(InvestorTradingDaily.date, InvestorTradingDaily.close_price)
            .filter(InvestorTradingDaily.symbol == code, InvestorTradingDaily.date <= target_date)
            .order_by(InvestorTradingDaily.date.desc()).first()
        )
        return jsonify({
            "status": "success",
            "code": code,
            "name": master.name if master else code,
            "market": master.market if master else "",
            "close_price": int(round(row[1])) if row else 0,
            "close_date": row[0] if row else None,
        })
    finally:
        session.close()


@paper_api_bp.route("/backtest-leaderboard", methods=["GET"])
def backtest_leaderboard():
    """시뮬레이션 리더보드/차트/매매일지 API. 파라미터 없는 기본 조회는 파일 캐시를 재사용합니다."""
    has_period = bool(request.args.get("period"))
    period = request.args.get("period", "3y").strip()
    custom_start = request.args.get("start_date", "").strip()
    custom_end = request.args.get("end_date", "").strip()

    # 기본 경로(파라미터 없음): backtest_run이 남긴 파일 캐시를 재조립 없이 반환
    if not has_period:
        cached = _read_render_cache()
        if cached is not None:
            return jsonify(cached)

    session = next(db_manager.get_session())
    try:
        from backend.app.services.backtest_leaderboard_builder import BacktestLeaderboardBuilder
        payload = BacktestLeaderboardBuilder(session).build(period, custom_start, custom_end, has_period)
        return jsonify(payload)
    finally:
        session.close()


MAX_SLOTS = 5  # 투자제안/모의투자 포트폴리오 최대 보유 종목 수


@paper_api_bp.route("/paper-trading/portfolio", methods=["GET"])
def get_portfolio():
    """계좌 유형(rec/prop)의 자산 상태와 보유 종목을 반환합니다.

    target_date(YYYY-MM-DD 또는 YYYYMMDD)가 오면 해당 기준일 종가로 보유 종목을 평가하고
    매도 신호(전략 매도 / -5% 손절 / +10% 익절)를 함께 산출합니다.
    """
    account_type = request.args.get("account_type", "rec").strip()
    target_date_raw = request.args.get("target_date", "").strip()
    session = next(db_manager.get_session())
    try:
        repo = PaperTradingRepository(session)
        pf = repo.get_or_create_portfolio(account_type=account_type)
        pos_dicts = [p.to_dict() for p in repo.get_positions(account_type=account_type)]

        positions, sell_signals, eval_date = pos_dicts, [], None
        stock_value = sum(p["buy_price"] * p["quantity"] for p in pos_dicts)
        if target_date_raw:
            from backend.app.services.proposal_advisor_cache import ProposalAdvisorCache
            td = _ymd(target_date_raw)
            view = ProposalAdvisorCache.get(session, td).build_portfolio_view(pos_dicts, td)
            positions, sell_signals = view["positions"], view["sell_signals"]
            stock_value, eval_date = view["stock_value"], view["eval_date"]

        total_asset = pf.cash_balance + stock_value

        # 추천 기준일(없으면 오늘) 시점의 코스피 20일선 방향(상승장/하락장/횡보) 산출
        from backend.app.services.kospi_regime_analyzer import KospiRegimeAnalyzer
        kospi_regime = KospiRegimeAnalyzer(session).analyze(_ymd(target_date_raw))

        return jsonify({
            "status": "success",
            "account_type": account_type,
            "eval_date": eval_date,
            "kospi_regime": kospi_regime,
            "portfolio": pf.to_dict(),
            "summary": {
                "initial_balance": int(pf.initial_balance),
                "cash_balance": int(pf.cash_balance),
                "stock_value": int(round(stock_value)),
                "total_asset": int(round(total_asset)),
                "profit_pct": round((total_asset - pf.initial_balance) / pf.initial_balance * 100.0, 2)
                if pf.initial_balance else 0.0,
                "holding_count": len(pos_dicts),
                "max_slots": MAX_SLOTS,
            },
            "positions": positions,
            "sell_signals": sell_signals,
        })
    finally:
        session.close()


@paper_api_bp.route("/paper-trading/reset", methods=["POST"])
def reset_portfolio():
    """지정된 계좌 유형(rec/prop)의 독립 자산 초기화 API."""
    req_data = request.get_json(silent=True) or {}
    account_type = req_data.get("account_type", "rec").strip()
    initial_balance = float(req_data.get("initial_balance", 10000000.0))

    session = next(db_manager.get_session())
    try:
        repo = PaperTradingRepository(session)
        pf = repo.reset_portfolio(account_type=account_type, initial_balance=initial_balance)
        return jsonify({
            "status": "success",
            "message": f"[{account_type.upper()}] 자산이 성공적으로 초기화되었습니다.",
            "portfolio": pf.to_dict()
        })
    finally:
        session.close()


@paper_api_bp.route("/paper-trading/manual-buy", methods=["POST"])
def manual_buy():
    """지정된 계좌 유형(rec/prop)의 수동 매수 실행 API."""
    req_data = request.get_json(silent=True) or {}
    account_type = req_data.get("account_type", "rec").strip()
    code = req_data.get("stock_code", "").strip()
    price = float(req_data.get("buy_price", 0))
    qty = int(req_data.get("quantity", 0))
    buy_date = req_data.get("buy_date", datetime.now().strftime("%Y-%m-%d"))

    if not code or price <= 0 or qty <= 0:
        return jsonify({"status": "error", "message": "올바른 종목코드, 단가, 수량을 입력해 주세요."}), 400

    session = next(db_manager.get_session())
    try:
        repo = PaperTradingRepository(session)
        pf = repo.get_or_create_portfolio(account_type=account_type)
        positions = repo.get_positions(account_type=account_type)
        total_cost = price * qty

        if len(positions) >= MAX_SLOTS:
            return jsonify({"status": "error", "message": f"보유 종목이 최대 {MAX_SLOTS}개로 가득 차 매수할 수 없습니다."}), 400
        if any(p.stock_code == code for p in positions):
            return jsonify({"status": "error", "message": "이미 보유 중인 종목입니다. (추가 매수/물타기 미지원)"}), 400
        if pf.cash_balance < total_cost:
            return jsonify({"status": "error", "message": f"잔여 현금({pf.cash_balance:,.0f}원)이 부족합니다."}), 400

        master = session.query(AllStockMaster).filter(AllStockMaster.code == code).first()
        stock_name = master.name if master else code

        pf.cash_balance -= total_cost
        repo.add_position(account_type, code, stock_name, buy_date, price, qty)
        repo.add_trade_history(account_type, buy_date, "MANUAL_BUY", code, stock_name, price, qty)
        session.commit()

        return jsonify({
            "status": "success",
            "message": f"[{account_type.upper()}] 계좌에 {stock_name}({code}) {qty}주 매수가 완료되었습니다.",
            "portfolio": pf.to_dict()
        })
    finally:
        session.close()


@paper_api_bp.route("/paper-trading/sell", methods=["POST"])
def sell_position():
    """지정된 계좌 유형(rec/prop)의 보유 종목 수동 매도(부분 매도 포함) 실행 API."""
    req_data = request.get_json(silent=True) or {}
    account_type = req_data.get("account_type", "rec").strip()
    code = req_data.get("stock_code", "").strip()
    price = float(req_data.get("sell_price", 0))
    qty = int(req_data.get("quantity", 0))
    sell_date = req_data.get("sell_date", datetime.now().strftime("%Y-%m-%d"))

    if not code or price <= 0 or qty <= 0:
        return jsonify({"status": "error", "message": "올바른 종목코드, 매도 단가, 수량을 입력해 주세요."}), 400

    session = next(db_manager.get_session())
    try:
        repo = PaperTradingRepository(session)
        pf = repo.get_or_create_portfolio(account_type=account_type)
        position = repo.get_position(account_type, code)

        if not position:
            return jsonify({"status": "error", "message": "보유하지 않은 종목입니다."}), 400
        if qty > position.quantity:
            return jsonify({"status": "error", "message": f"보유 수량({position.quantity}주)을 초과해 매도할 수 없습니다."}), 400

        proceeds = price * qty
        realized_pnl = (price - position.buy_price) * qty
        stock_name = position.stock_name

        pf.cash_balance += proceeds
        repo.reduce_position(position, qty)
        repo.add_trade_history(account_type, sell_date, "SELL", code, stock_name, price, qty, realized_pnl)
        session.commit()

        return jsonify({
            "status": "success",
            "message": f"[{account_type.upper()}] {stock_name}({code}) {qty}주 매도 완료 "
                       f"(실현손익 {realized_pnl:+,.0f}원).",
            "portfolio": pf.to_dict(),
            "realized_pnl": int(round(realized_pnl)),
        })
    finally:
        session.close()
