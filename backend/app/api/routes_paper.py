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

        # 백테스트 결과 3개 테이블 전체 초기화 후 단일 전략만 재연산.
        # S1b/S1c 폐기(Phase 1) → combo_id 1·2·5·6·7·8 (6종). 결번 유지.
        StrategyLeaderboardRepository(session).clear_all()
        StrategyTradeLogsRepository(session).clear_all()
        StrategyDailyEquityRepository(session).clear_all()

        combo_ids = [1, 2, 5, 6, 7, 8]
        total_steps = len(combo_ids) + 1  # + 순수관행 엔트리
        engine = BacktestEngine(session)
        for i, c_id in enumerate(combo_ids, 1):
            try:
                engine.run_backtest_for_combo(
                    combo_id=c_id,
                    initial_capital=10000000.0,
                    max_slots=5,  # Phase 2: 전 백테스트 5슬롯 통일
                    start_date=start_date,
                    end_date=end_date,
                    target_sectors=["KOSPI 200", "KOSDAQ 150"]
                )
            except Exception as e:
                logger.error(f"Combo {c_id} 오류: {e}")
            BACKTEST_PROGRESS["completed"] = i
            BACKTEST_PROGRESS["message"] = f"전략 조합 {i}/{total_steps} 연산 완료..."

        # 순수관행(횡단면 합성 점수) 엔트리 — combo_id=22
        try:
            from backend.app.services.purerule_engine import PureRuleEngine
            PureRuleEngine(session).run_backtest(
                initial_capital=10000000.0, max_slots=5,
                start_date=start_date, end_date=end_date,
                target_sectors=["KOSPI 200", "KOSDAQ 150"],
            )
        except Exception as e:
            logger.error(f"순수관행 엔트리 오류: {e}")
        BACKTEST_PROGRESS["completed"] = total_steps
        BACKTEST_PROGRESS["message"] = f"전략 조합 {total_steps}/{total_steps} 연산 완료..."

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


def _dash(ymd: str) -> str:
    """'YYYYMMDD'를 'YYYY-MM-DD'로 변환합니다(형식이 아니면 원본 반환)."""
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}" if ymd and len(ymd) == 8 and ymd.isdigit() else ymd


def _paper_session(account_type: str):
    """paper_* 테이블 작업용 세션을 계좌유형별로 연다(전용 엔진 없으면 메인과 동일).

    시세·마스터 조회는 항상 메인 세션(`db_manager.get_session()`)을 별도로 쓴다.
    """
    return next(db_manager.get_paper_session(account_type))


def _close_on_or_before(session, code: str, ymd: str):
    """종목의 기준일(YYYYMMDD) 이하 최근 거래일 종가와 그 거래일을 반환합니다.

    :return: (종가float, 거래일'YYYYMMDD'). 데이터가 없으면 (None, None).
    """
    from backend.app.models.investor_trading_daily import InvestorTradingDaily
    row = (
        session.query(InvestorTradingDaily.date, InvestorTradingDaily.close_price)
        .filter(InvestorTradingDaily.symbol == code, InvestorTradingDaily.date <= ymd)
        .order_by(InvestorTradingDaily.date.desc()).first()
    )
    return (float(row[1]), row[0]) if row else (None, None)


@paper_api_bp.route("/recommended-stocks", methods=["GET"])
def recommended_stocks():
    """S1~S5(6전략) 전략별 TOP 3 매수 추천 종목 반환 API.

    mode=advice(기본, 투자제안): 신호 판단일=기준일(D-0).
    mode=sim(모의투자): 신호 판단일=기준일 직전 거래일(D-1), 추천가는 기준일(D-0) 종가.
    """
    target_date = _ymd(request.args.get("target_date") or request.args.get("date"))
    mode = "sim" if request.args.get("mode") == "sim" else "advice"
    session = next(db_manager.get_session())
    try:
        from backend.app.services.proposal_advisor_cache import ProposalAdvisorCache
        adv = ProposalAdvisorCache.get(session, target_date, mode)
        result = adv.get_recommendations(target_date)
        # 순수관행 합성 점수 TOP 10 (신호 유무 무관)
        result["composite_top"] = adv.get_composite_top(target_date, n=10)["data"]
        return jsonify({"status": "success", **result})
    finally:
        session.close()


@paper_api_bp.route("/paper-trading/next-trading-date", methods=["GET"])
def next_trading_date():
    """거래일 달력에서 입력일보다 큰 첫 거래일을 'YYYY-MM-DD'로 반환합니다.

    모의투자 '다음날 조회'용. 주말·공휴일은 달력에 없으므로 자연히 건너뜁니다.
    추천/평가 연산이 쓰는 수급 일별 데이터(investor_trading_daily)의 거래일을 그대로 사용해,
    엔진의 기준일 스냅(직전 거래일로 되돌림)과 어긋나지 않게 합니다.
    다음 거래일이 없으면(마지막 거래일) next_date=None을 반환합니다.
    """
    base = _ymd(request.args.get("date") or request.args.get("target_date"))
    session = next(db_manager.get_session())
    try:
        from backend.app.models.investor_trading_daily import InvestorTradingDaily
        row = (
            session.query(InvestorTradingDaily.date)
            .filter(InvestorTradingDaily.date > base)
            .order_by(InvestorTradingDaily.date.asc()).first()
        )
        return jsonify({"status": "success", "next_date": _dash(row[0]) if row else None})
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
PAPER_EXPORT_SCHEMA = 1  # 가상매매 JSON 내보내기/불러오기 스키마 버전


@paper_api_bp.route("/paper-trading/portfolio", methods=["GET"])
def get_portfolio():
    """계좌 유형(rec/prop)의 자산 상태와 보유 종목을 반환합니다.

    target_date(YYYY-MM-DD 또는 YYYYMMDD)가 오면 해당 기준일 종가로 보유 종목을 평가하고
    매도 신호(전략 매도 / -5% 손절 / +10% 익절)를 함께 산출합니다.
    """
    account_type = request.args.get("account_type", "rec").strip()
    target_date_raw = request.args.get("target_date", "").strip()
    mode = "sim" if request.args.get("mode") == "sim" else "advice"
    session = next(db_manager.get_session())          # 시세·지표·코스피용(메인)
    psession = _paper_session(account_type)           # 자산·보유용(계좌유형별)
    try:
        repo = PaperTradingRepository(psession)
        pf = repo.get_or_create_portfolio(account_type=account_type)
        pos_dicts = [p.to_dict() for p in repo.get_positions(account_type=account_type)]

        positions, sell_signals, eval_date, signal_date = pos_dicts, [], None, None
        stock_value = sum(p["buy_price"] * p["quantity"] for p in pos_dicts)
        if target_date_raw:
            from backend.app.services.proposal_advisor_cache import ProposalAdvisorCache
            td = _ymd(target_date_raw)
            view = ProposalAdvisorCache.get(session, td, mode).build_portfolio_view(pos_dicts, td)
            positions, sell_signals = view["positions"], view["sell_signals"]
            stock_value, eval_date = view["stock_value"], view["eval_date"]
            signal_date = view["signal_date"]

        total_asset = pf.cash_balance + stock_value

        # 추천 기준일(없으면 오늘) 시점의 코스피 20일선 방향(상승장/하락장/횡보) 산출
        from backend.app.services.kospi_regime_analyzer import KospiRegimeAnalyzer
        kospi_regime = KospiRegimeAnalyzer(session).analyze(_ymd(target_date_raw))

        return jsonify({
            "status": "success",
            "account_type": account_type,
            "eval_date": eval_date,
            "signal_date": signal_date,
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
        psession.close()


@paper_api_bp.route("/paper-trading/reset", methods=["POST"])
def reset_portfolio():
    """지정된 계좌 유형(rec/prop)의 독립 자산 초기화 API."""
    req_data = request.get_json(silent=True) or {}
    account_type = req_data.get("account_type", "rec").strip()
    initial_balance = float(req_data.get("initial_balance", 10000000.0))

    psession = _paper_session(account_type)
    try:
        repo = PaperTradingRepository(psession)
        pf = repo.reset_portfolio(account_type=account_type, initial_balance=initial_balance)
        return jsonify({
            "status": "success",
            "message": f"[{account_type.upper()}] 자산이 성공적으로 초기화되었습니다.",
            "portfolio": pf.to_dict()
        })
    finally:
        psession.close()


@paper_api_bp.route("/paper-trading/manual-buy", methods=["POST"])
def manual_buy():
    """지정된 계좌 유형(rec/prop)의 수동 매수 실행 API.

    rec 계좌: 단가 미입력 시 기준일(buy_date) 이하 최근 거래일 종가를 기본 체결가로 쓰고,
    수량 미입력 시 (현재 총자산 ÷ 최대 슬롯 ÷ 단가)를 잔여 현금 한도 내에서 내림 산정합니다.
    사용자가 값을 보내면 그 값을 그대로 존중합니다.
    """
    req_data = request.get_json(silent=True) or {}
    account_type = req_data.get("account_type", "rec").strip()
    code = req_data.get("stock_code", "").strip()
    price = float(req_data.get("buy_price", 0) or 0)
    qty = int(req_data.get("quantity", 0) or 0)
    buy_date = req_data.get("buy_date", datetime.now().strftime("%Y-%m-%d"))
    # 추천 카드에서 매수 시 어느 전략/순수관행이 제안했는지 태그(없으면 MANUAL)
    entry_strategy = (req_data.get("strategy") or req_data.get("entry_strategy") or "MANUAL").strip()[:20]

    if not code:
        return jsonify({"status": "error", "message": "종목코드를 입력해 주세요."}), 400

    session = next(db_manager.get_session())          # 시세·마스터용(메인)
    psession = _paper_session(account_type)           # 자산·보유용(계좌유형별)
    try:
        repo = PaperTradingRepository(psession)
        pf = repo.get_or_create_portfolio(account_type=account_type)
        positions = repo.get_positions(account_type=account_type)

        # rec 계좌: 단가·수량 기본값을 기준일 종가 기반으로 자동 산정
        if account_type == "rec":
            eff_close, eff_date = _close_on_or_before(session, code, _ymd(buy_date))
            if price <= 0:
                if not eff_close:
                    return jsonify({"status": "error", "message": "기준일 종가를 찾을 수 없어 매수할 수 없습니다(거래정지/데이터 없음)."}), 400
                price = eff_close
            if eff_date:
                buy_date = _dash(eff_date)
            if qty <= 0 and price > 0:
                held_val = sum(
                    p.quantity * (_close_on_or_before(session, p.stock_code, _ymd(buy_date))[0] or p.buy_price)
                    for p in positions
                )
                slot_budget = (pf.cash_balance + held_val) / MAX_SLOTS
                qty = int(min(slot_budget, pf.cash_balance) // price)

        if price <= 0 or qty <= 0:
            return jsonify({"status": "error", "message": "올바른 단가와 수량을 입력해 주세요."}), 400

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
        repo.add_position(account_type, code, stock_name, buy_date, price, qty, entry_strategy=entry_strategy)
        repo.add_trade_history(account_type, buy_date, "MANUAL_BUY", code, stock_name, price, qty,
                               entry_strategy=entry_strategy)
        psession.commit()

        return jsonify({
            "status": "success",
            "message": f"[{account_type.upper()}] 계좌에 {stock_name}({code}) {qty}주 매수가 완료되었습니다.",
            "portfolio": pf.to_dict()
        })
    finally:
        session.close()
        psession.close()


@paper_api_bp.route("/paper-trading/sell", methods=["POST"])
def sell_position():
    """지정된 계좌 유형(rec/prop)의 보유 종목 수동 매도(부분 매도 포함) 실행 API.

    rec 계좌: 매도 단가 미입력 시 기준일(sell_date) 이하 최근 거래일 종가를 기본가로 씁니다.
    """
    req_data = request.get_json(silent=True) or {}
    account_type = req_data.get("account_type", "rec").strip()
    code = req_data.get("stock_code", "").strip()
    price = float(req_data.get("sell_price", 0) or 0)
    qty = int(req_data.get("quantity", 0) or 0)
    sell_date = req_data.get("sell_date", datetime.now().strftime("%Y-%m-%d"))

    if not code or qty <= 0:
        return jsonify({"status": "error", "message": "올바른 종목코드와 수량을 입력해 주세요."}), 400

    session = next(db_manager.get_session())          # 시세용(메인)
    psession = _paper_session(account_type)           # 자산·보유용(계좌유형별)
    try:
        repo = PaperTradingRepository(psession)
        pf = repo.get_or_create_portfolio(account_type=account_type)
        position = repo.get_position(account_type, code)

        if not position:
            return jsonify({"status": "error", "message": "보유하지 않은 종목입니다."}), 400
        if qty > position.quantity:
            return jsonify({"status": "error", "message": f"보유 수량({position.quantity}주)을 초과해 매도할 수 없습니다."}), 400

        # rec 계좌: 단가 미입력 시 기준일 종가를 기본 매도가로 사용
        if account_type == "rec" and price <= 0:
            eff_close, eff_date = _close_on_or_before(session, code, _ymd(sell_date))
            if not eff_close:
                return jsonify({"status": "error", "message": "기준일 종가를 찾을 수 없어 매도할 수 없습니다(거래정지/데이터 없음)."}), 400
            price = eff_close
            if eff_date:
                sell_date = _dash(eff_date)

        if price <= 0:
            return jsonify({"status": "error", "message": "올바른 매도 단가를 입력해 주세요."}), 400

        proceeds = price * qty
        realized_pnl = (price - position.buy_price) * qty
        stock_name = position.stock_name

        pf.cash_balance += proceeds
        repo.reduce_position(position, qty)
        repo.add_trade_history(account_type, sell_date, "SELL", code, stock_name, price, qty, realized_pnl)
        psession.commit()

        return jsonify({
            "status": "success",
            "message": f"[{account_type.upper()}] {stock_name}({code}) {qty}주 매도 완료 "
                       f"(실현손익 {realized_pnl:+,.0f}원).",
            "portfolio": pf.to_dict(),
            "realized_pnl": int(round(realized_pnl)),
        })
    finally:
        session.close()
        psession.close()


@paper_api_bp.route("/proposal/notify-recommendations", methods=["POST"])
def notify_recommendations():
    """현재 기준일의 투자제안 매수 추천 + prop 보유 매도 시그널을 디스코드로 전달합니다.

    매수 추천은 종목코드 기준 병합(전략별 확률 표기), 매도는 prop 계좌 보유 종목의 기준일
    매도 신호를 대상으로 한다. 매수·매도 모두 0개면 '추천 없음' 안내를 발송한다(미발송 아님).
    """
    req = request.get_json(silent=True) or {}
    target_date = _ymd(req.get("target_date"))
    session = next(db_manager.get_session())          # 시세·지표용(메인)
    psession = _paper_session("prop")                 # prop 보유 종목용
    try:
        from backend.app.services.proposal_advisor_cache import ProposalAdvisorCache
        from backend.app.services.proposal_notify_builder import ProposalNotifyBuilder
        from backend.app.services.discord_notifier import DiscordNotifier

        # 투자제안(advice) 모드 — /api/recommended-stocks / portfolio 와 동일 소스
        adv = ProposalAdvisorCache.get(session, target_date, "advice")
        rec = adv.get_recommendations(target_date)
        pos_dicts = [p.to_dict() for p in PaperTradingRepository(psession).get_positions(account_type="prop")]
        view = adv.build_portfolio_view(pos_dicts, target_date)

        message, buy_n, sell_n = ProposalNotifyBuilder().build(
            _dash(target_date), _dash(rec.get("eval_date") or target_date),
            rec.get("data", []), view.get("sell_signals", []),
        )
        result = DiscordNotifier().send(message)
        if not result["ok"]:
            return jsonify({"status": "error", "message": result["message"]}), 502
        return jsonify({"status": "success", "buy_count": buy_n, "sell_count": sell_n})
    finally:
        session.close()
        psession.close()


@paper_api_bp.route("/paper-trading/export", methods=["GET"])
def export_paper_account():
    """가상매매 계좌(계좌·보유·체결)를 스키마 버전 포함 단일 JSON으로 반환합니다(백업/이동용)."""
    account_type = request.args.get("account_type", "prop").strip()
    psession = _paper_session(account_type)
    try:
        data = PaperTradingRepository(psession).export_account(account_type)
        return jsonify({
            "schema_version": PAPER_EXPORT_SCHEMA,
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "account_type": account_type,
            **data,
        })
    finally:
        psession.close()


@paper_api_bp.route("/paper-trading/import", methods=["POST"])
def import_paper_account():
    """업로드된 JSON으로 가상매매 계좌를 전체 교체하고, 교체 직전 상태를 backup으로 함께 반환합니다."""
    payload = request.get_json(silent=True) or {}
    account_type = (payload.get("account_type") or request.args.get("account_type") or "prop").strip()

    if int(payload.get("schema_version", 0) or 0) != PAPER_EXPORT_SCHEMA:
        return jsonify({"status": "error", "message": f"스키마 버전이 맞지 않습니다(기대값 {PAPER_EXPORT_SCHEMA})."}), 400
    if not isinstance(payload.get("portfolio"), dict) or not isinstance(payload.get("positions"), list):
        return jsonify({"status": "error", "message": "portfolio(dict)/positions(list) 필드가 올바르지 않습니다."}), 400

    psession = _paper_session(account_type)
    try:
        repo = PaperTradingRepository(psession)
        backup = repo.export_account(account_type)  # 교체 전 스냅샷(자동 백업용)
        imported = repo.replace_account(account_type, payload)
        return jsonify({
            "status": "success",
            "imported": imported,
            "backup": {"schema_version": PAPER_EXPORT_SCHEMA, "account_type": account_type, **backup},
        })
    finally:
        psession.close()


@paper_api_bp.route("/paper-trading/sync-turso", methods=["POST"])
def sync_turso():
    """로컬 prop 계좌를 Turso와 한 번에 동기화한다(direction=push|pull, prop 전용).

    push: 로컬(app.db) → Turso 전체 교체 / pull: Turso → 로컬 전체 교체.
    교체되는 쪽의 직전 상태를 backup으로 함께 반환한다.
    앱이 이미 Turso 드라이버로 직접 연결된 경우(배포 환경)에는 동기화가 불필요하다.
    """
    from backend.app.services.turso_http_client import TursoHttpClient

    direction = (request.args.get("direction") or "").strip()
    if direction not in ("push", "pull"):
        return jsonify({"status": "error", "message": "direction 은 push 또는 pull 이어야 합니다."}), 400
    if db_manager.paper_engine is not None:
        return jsonify({"status": "error", "message": "이미 Turso에 직접 연결돼 있어 동기화가 필요 없습니다."}), 400

    client = TursoHttpClient()
    if not client.configured:
        return jsonify({"status": "error", "message": "PAPER_DATABASE_URL(호스트·authToken)이 설정되지 않았습니다(.env 확인)."}), 400

    psession = _paper_session("prop")  # 로컬 메인 DB(app.db)
    try:
        repo = PaperTradingRepository(psession)
        if direction == "push":
            payload = {"schema_version": PAPER_EXPORT_SCHEMA, **repo.export_account("prop")}
            backup = client.fetch_account()          # Turso 직전 상태(백업)
            imported = client.overwrite_account(payload)
        else:  # pull
            remote = client.fetch_account()
            backup = repo.export_account("prop")      # 로컬 직전 상태(백업)
            imported = repo.replace_account("prop", {"schema_version": PAPER_EXPORT_SCHEMA, **remote})
        return jsonify({
            "status": "success",
            "direction": direction,
            "imported": imported,
            "backup": {"schema_version": PAPER_EXPORT_SCHEMA, "account_type": "prop", **backup},
        })
    except Exception as exc:  # HTTP·SQL 오류를 사용자 메시지로
        logging.getLogger(__name__).exception("Turso 동기화 실패")
        return jsonify({"status": "error", "message": f"Turso 동기화 실패: {exc}"}), 502
    finally:
        psession.close()
