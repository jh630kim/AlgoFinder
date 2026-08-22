"""
모의투자(account_type='rec') 및 투자제안(account_type='prop') 분리 API 라우트 모듈 (routes_paper.py).

계좌유형별 독립 자산 관리(reset, buy, sell, manual-buy) 및 백테스트 리더보드 API를 담당합니다.
"""

from datetime import datetime
from flask import Blueprint, request, jsonify
from backend.app.core.database import db_manager
from backend.app.repositories.paper_trading_repository import PaperTradingRepository
from backend.app.models.all_stock_master import AllStockMaster

paper_api_bp = Blueprint("paper_api", __name__, url_prefix="/api")


@paper_api_bp.route("/recommended-stocks", methods=["GET"])
def recommended_stocks():
    """전략별 매수 포착 추천 종목 반환 API."""
    target_date = request.args.get("date", "").strip()
    sample_recommendations = [
        {
            "code": "011200",
            "name": "HMM",
            "market": "KOSPI",
            "win_rate": 78.8,
            "target_price": 21700.0,
            "strategy_name": "🟠 S3 볼린저 밴드 전략",
            "reason": "💡 볼린저 밴드 수축(Squeeze) 후 상한선 강한 폭발 돌파 포착",
            "target_profit_loss": "1:2.5",
        },
        {
            "code": "005930",
            "name": "삼성전자",
            "market": "KOSPI",
            "win_rate": 82.4,
            "target_price": 78500.0,
            "strategy_name": "🟡 S1c 20일선 적용형",
            "reason": "💡 기관/외국인 동시 쌍끌이 순매수 유입 및 눌림목 반등 포착",
            "target_profit_loss": "1:3.0",
        }
    ]
    return jsonify({"status": "success", "date": target_date or datetime.now().strftime("%Y-%m-%d"), "data": sample_recommendations})


@paper_api_bp.route("/backtest-leaderboard", methods=["GET"])
def backtest_leaderboard():
    """시뮬레이션 내림차순 리더보드 및 매매일지 API."""
    period = request.args.get("period", "3y").strip()
    leaderboard = [
        {"rank": 1, "strategy": "S4", "eval_amount": 28372278, "return_rate": 183.72, "win_rate": 63.71, "mdd": -56.03, "trade_count": 394},
        {"rank": 2, "strategy": "S1c", "eval_amount": 24520000, "return_rate": 145.20, "win_rate": 68.50, "mdd": -42.10, "trade_count": 312},
        {"rank": 3, "strategy": "S2", "eval_amount": 21250000, "return_rate": 112.50, "win_rate": 61.20, "mdd": -48.30, "trade_count": 280},
    ]
    trade_logs = [
        {
            "date": "2014-06-12", "name": "솔브레인홀딩스", "code": "036830", "type": "매수S4",
            "days": "1일", "quantity": 59, "price": 33400, "total": 1970600,
            "cum_asset": "10,000,000원 (+0%)", "pnl": "-"
        }
    ]
    return jsonify({"status": "success", "period": period, "leaderboard": leaderboard, "trade_logs": trade_logs})


@paper_api_bp.route("/paper-trading/portfolio", methods=["GET"])
def get_portfolio():
    """지정된 계좌 유형(rec/prop)의 독립 자산 상태 및 보유 종목 리스트 반환 API."""
    account_type = request.args.get("account_type", "rec").strip()
    session = next(db_manager.get_session())
    try:
        repo = PaperTradingRepository(session)
        pf = repo.get_or_create_portfolio(account_type=account_type)
        pos_list = repo.get_positions(account_type=account_type)
        return jsonify({
            "status": "success",
            "account_type": account_type,
            "portfolio": pf.to_dict(),
            "positions": [p.to_dict() for p in pos_list],
            "sell_signals": []
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
        total_cost = price * qty

        if pf.cash_balance < total_cost:
            return jsonify({"status": "error", "message": f"잔여 현금({pf.cash_balance:,.0f}원)이 부족합니다."}), 400

        master = session.query(AllStockMaster).filter(AllStockMaster.code == code).first()
        stock_name = master.name if master else code

        pf.cash_balance -= total_cost
        repo.add_trade_history(account_type, buy_date, "MANUAL_BUY", code, stock_name, price, qty)
        session.commit()

        return jsonify({
            "status": "success",
            "message": f"[{account_type.upper()}] 계좌에 {stock_name}({code}) {qty}주 매수가 완료되었습니다.",
            "portfolio": pf.to_dict()
        })
    finally:
        session.close()
