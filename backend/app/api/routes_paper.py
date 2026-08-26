"""
모의투자(account_type='rec') 및 투자제안(account_type='prop') 분리 API 라우트 모듈 (routes_paper.py).

계좌유형별 독립 자산 관리(reset, buy, sell, manual-buy) 및 백테스트 리더보드 API를 담당합니다.
"""

import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from backend.app.core.database import db_manager
from backend.app.repositories.paper_trading_repository import PaperTradingRepository
from backend.app.models.all_stock_master import AllStockMaster

logger = logging.getLogger(__name__)
paper_api_bp = Blueprint("paper_api", __name__, url_prefix="/api")

BACKTEST_PROGRESS = {
    "status": "idle",
    "completed": 0,
    "total": 21,
    "message": ""
}

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

        engine = BacktestEngine(session)
        for c_id in range(1, 22):
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
            BACKTEST_PROGRESS["message"] = f"전략 조합 {c_id}/21 연산 완료..."
            
        BACKTEST_PROGRESS["status"] = "completed"
        BACKTEST_PROGRESS["message"] = "백테스트 완료"
        return jsonify({"status": "success", "message": "백테스트가 성공적으로 완료되었습니다."})
    except Exception as e:
        BACKTEST_PROGRESS["status"] = "error"
        BACKTEST_PROGRESS["message"] = f"오류 발생: {str(e)}"
        return jsonify({"status": "error", "message": str(e)})
    finally:
        session.close()


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
    """시뮬레이션 내림차순 리더보드, 백테스트 차트 및 매매일지 API (DB 및 기간 연산)."""
    period = request.args.get("period", "3y").strip()
    custom_start = request.args.get("start_date", "").strip()
    custom_end = request.args.get("end_date", "").strip()
    
    session = next(db_manager.get_session())
    try:
        from backend.app.models.market_indices_daily import MarketIndicesDaily
        from backend.app.repositories.strategy_leaderboard_repository import StrategyLeaderboardRepository
        from backend.app.repositories.strategy_trade_logs_repository import StrategyTradeLogsRepository
        from backend.app.repositories.strategy_daily_equity_repository import StrategyDailyEquityRepository

        # 0. DB에 저장된 실제 기간 추론 (최초 접속 시 화면 동기화용)
        # 파라미터가 없으면 DB에 저장된 연산 일수를 기반으로 period를 강제 적용합니다.
        from backend.app.models.strategy_leaderboard import StrategyLeaderboard
        db_entries_count = session.query(StrategyLeaderboard).count()
        if db_entries_count > 0 and not request.args.get("period"):
            from backend.app.models.strategy_daily_equity import StrategyDailyEquity
            db_period_days = session.query(StrategyDailyEquity.trade_date).distinct().count()
            if db_period_days > 0:
                if db_period_days <= 150: period = "6m"
                elif db_period_days <= 300: period = "1y"
                elif db_period_days <= 800: period = "3y"
                elif db_period_days <= 1500: period = "5y"
                else: period = "all"
        
        # 1. KOSPI 지수 및 20일 이동평균 수식 100% 백엔드 연산
        records = session.query(MarketIndicesDaily).order_by(MarketIndicesDaily.date.asc()).all()
        kospi_chart_data = []
        if records:
            valid_recs = [r for r in records if r.kospi_close is not None]
            closes = [r.kospi_close for r in valid_recs]
            dates = [r.date for r in valid_recs]
            ma20_list = [None] * len(closes)
            for i in range(19, len(closes)):
                window = closes[i-19:i+1]
                ma20_list[i] = round(sum(window) / 20.0, 2)
            
            # 시뮬레이션 기간 매핑 (6m: 125일, 1y: 250일, 3y: 750일, 5y: 1250일, all: 5000일, custom: 날짜 범위)
            if period == "custom" and custom_start and custom_end:
                # 커스텀 날짜 인덱싱
                start_fmt = custom_start.replace("-", "")
                end_fmt = custom_end.replace("-", "")
                filtered_indices = [i for i, d in enumerate(dates) if start_fmt <= d <= end_fmt]
                if filtered_indices:
                    target_closes = [closes[i] for i in filtered_indices]
                    target_dates = [dates[i] for i in filtered_indices]
                    target_ma20 = [ma20_list[i] for i in filtered_indices]
                else:
                    target_closes, target_dates, target_ma20 = closes[-750:], dates[-750:], ma20_list[-750:]
            else:
                period_limits = {"6m": 125, "1y": 250, "3y": 750, "5y": 1250, "all": 5000}
                limit = period_limits.get(period, 750)
                target_closes = closes[-limit:]
                target_dates = dates[-limit:]
                target_ma20 = ma20_list[-limit:]

            for i in range(len(target_closes)):
                d_str = target_dates[i]
                if len(d_str) == 8:
                    d_str = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
                kospi_chart_data.append({
                    "date": d_str,
                    "kospi_close": target_closes[i],
                    "kospi_ma20": target_ma20[i]
                })

        # 2. DB 초고속 조회 (Fast Query) 전환 (HTTP 타임아웃 100% 방지)
        leaderboard_repo = StrategyLeaderboardRepository(session)
        db_entries = leaderboard_repo.get_all_ordered_by_return()

        # 만약 DB 리더보드가 없으면 강제 실행하지 않고 빈 상태를 유지 (프론트에서 수동 실행 필요)
        if not db_entries:
            db_entries = []
        full_combos = []
        for idx, entry in enumerate(db_entries):
            full_combos.append({
                "rank": idx + 1,
                "combo_id": entry.combo_id,
                "strategy": entry.combo_name.split(" ")[0] if " " in entry.combo_name else entry.combo_name,
                "name": entry.combo_name,
                "eval_amount": int(entry.final_capital),
                "return_rate": round(entry.total_return_pct, 2),
                "win_rate": round(entry.win_rate_pct, 2),
                "mdd": round(entry.mdd_pct, 2),
                "trade_count": entry.total_trades
            })

        # DB 매매 일지 (strategy_trade_logs) 전체 전략별 쿼리
        from backend.app.models.strategy_trade_logs import StrategyTradeLogs
        all_db_logs = session.query(StrategyTradeLogs).order_by(StrategyTradeLogs.trade_date.asc()).all()
        combo_to_strat = {combo["combo_id"]: combo["strategy"] for combo in full_combos}
        
        trade_logs_map = {}
        # 차트 매수/매도 마커 이벤트 (전략별 → 날짜별 이벤트 리스트)
        chart_trade_events = {}

        for log in all_db_logs:
            stk_key = combo_to_strat.get(log.combo_id)
            if not stk_key:
                continue
            if stk_key not in trade_logs_map:
                trade_logs_map[stk_key] = []
            if stk_key not in chart_trade_events:
                chart_trade_events[stk_key] = []
            
            d_str = log.trade_date
            if len(d_str) == 8:
                d_str = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
            
            trade_logs_map[stk_key].append({
                "date": d_str,
                "name": log.name,
                "code": log.symbol,
                "type": f"{'매수' if log.trade_type == 'BUY' else '매도'}{log.strategy_tag}",
                "days": f"{log.holding_days}일",
                "quantity": log.shares,
                "price": int(log.unit_price),
                "total": int(log.total_amount),
                "cum_asset": f"{int(log.equity_after_trade):,}원 ({'+' if log.cum_return_pct >= 0 else ''}{log.cum_return_pct}%)",
                "equity_raw": int(log.equity_after_trade),
                "slot_no": log.slot_no or 0,
                "pnl": f"{'+' if log.profit_krw > 0 else ''}{int(log.profit_krw):,}원 ({'+' if log.profit_pct >= 0 else ''}{log.profit_pct}%)" if log.trade_type == "SELL" else "-"
            })

            # 차트 마커용 이벤트 등록 (날짜, 매수/매도, 슬롯 번호, 종목명)
            chart_trade_events[stk_key].append({
                "date": d_str,
                "trade_type": log.trade_type,
                "slot_no": log.slot_no or 0,
                "name": log.name,
                "symbol": log.symbol
            })


        # DB에서 일별 누적자산(StrategyDailyEquity) 쿼리
        equity_repo = StrategyDailyEquityRepository(session)
        combo_equity_maps = {}
        for combo in full_combos:
            combo_id = combo["combo_id"]
            eq_records = equity_repo.get_equity_by_combo(combo_id)
            combo_equity_maps[combo_id] = {r.trade_date: r.equity_amount for r in eq_records}

        # 4. 차트 일별 자산 시계열 (100% DB/엔진 연산 기반)
        n_days = len(kospi_chart_data)
        combo_last_equity = {combo["combo_id"]: 10000000.0 for combo in full_combos}
        
        for i in range(n_days):
            date_str = kospi_chart_data[i]["date"]
            db_date = date_str.replace("-", "")
            asset_map = {}
            for combo in full_combos:
                stk_key = combo["strategy"]
                combo_id = combo["combo_id"]
                eq_map = combo_equity_maps[combo_id]
                
                if db_date in eq_map:
                    combo_last_equity[combo_id] = eq_map[db_date]
                
                asset_map[stk_key] = round(combo_last_equity[combo_id], 0)
            kospi_chart_data[i]["strategy_assets"] = asset_map

        return jsonify({
            "status": "success",
            "period": period,
            "leaderboard": full_combos,
            "trade_logs": trade_logs_map,
            "chart_trade_events": chart_trade_events,
            "chart_data": kospi_chart_data
        })
    finally:
        session.close()


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
