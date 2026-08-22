"""
웹 대시보드 전용 최적화 쿼리 레포지토리 (web_repository.py).

종목 자동완성, OHLCV 및 4대 주체 수급 차트, TOP 20 수급 랭킹, 지수 summary,
TargetStocks 구분 및 연쇄 업종(industry) / 수급 종목 4단계 필터링 조회를 담당하며,
구분/업종 전체 항목의 날짜별 평균 주가 및 전체 수급 집계 쿼리를 제공합니다.
"""

import logging
import pandas as pd
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_
from backend.app.models.all_stock_master import AllStockMaster
from backend.app.models.target_stocks import TargetStocks
from backend.app.models.investor_trading_daily import InvestorTradingDaily
from backend.app.models.sync_logs import SyncLogs
from backend.app.models.market_indices_daily import MarketIndicesDaily
from backend.app.services.strategies.s1c_ma_cross_adaptive import S1cMACrossAdaptiveStrategy

logger = logging.getLogger(__name__)


class WebRepository:
    """웹 대시보드 데이터 조회 전담 레포지토리 클래스."""

    def __init__(self, session: Session):
        """DB 세션을 초기화합니다."""
        self.session = session

    def search_stocks(self, query_str: str, limit: int = 15) -> List[Dict[str, Any]]:
        """종목코드 또는 종목명으로 자동완성 검색을 수행합니다."""
        if not query_str:
            stocks = self.session.query(AllStockMaster).limit(limit).all()
        else:
            q = f"%{query_str}%"
            stocks = self.session.query(AllStockMaster).filter(
                or_(AllStockMaster.code.like(q), AllStockMaster.name.like(q))
            ).limit(limit).all()

        return [
            {
                "code": s.code,
                "name": s.name,
                "market": s.market,
                "industry": s.industry or "",
            }
            for s in stocks
        ]

    def get_target_categories(self) -> List[str]:
        """target_stocks에 등록된 종목들의 유일한 sector/market 구분 리스트를 반환합니다."""
        sectors = (
            self.session.query(AllStockMaster.sector)
            .join(TargetStocks, AllStockMaster.code == TargetStocks.symbol)
            .distinct()
            .all()
        )
        cat_list = [c[0] for c in sectors if c[0]]
        if "KOSPI 200" not in cat_list:
            cat_list.insert(0, "KOSPI 200")
        if "KOSDAQ 150" not in cat_list:
            cat_list.append("KOSDAQ 150")
        return cat_list

    def get_target_industries(self, category: Optional[str] = None) -> List[str]:
        """선택된 구분에 속한 target_stocks 종목들의 유일한 industry 업종 리스트를 반환합니다."""
        q = self.session.query(AllStockMaster.industry).join(TargetStocks, AllStockMaster.code == TargetStocks.symbol)
        if category and category != "ALL":
            q = q.filter(or_(AllStockMaster.sector == category, AllStockMaster.market == category))
        industries = q.distinct().all()
        return [ind[0] for ind in industries if ind[0]]

    def get_filtered_target_stocks(self, category: Optional[str] = None, industry: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        선택된 구분 및 업종 조건으로 InvestorTradingDaily 수급 데이터가 실제 저장되어 있는
        유일 종목 리스트를 시가총액(marcap) 내림차순으로 반환합니다.
        """
        q = (
            self.session.query(AllStockMaster.code, AllStockMaster.name, AllStockMaster.market, AllStockMaster.marcap)
            .join(InvestorTradingDaily, AllStockMaster.code == InvestorTradingDaily.symbol)
        )
        if category and category != "ALL":
            q = q.filter(or_(AllStockMaster.sector == category, AllStockMaster.market == category))
        if industry and industry != "ALL":
            q = q.filter(AllStockMaster.industry == industry)

        results = q.group_by(AllStockMaster.code).order_by(desc(AllStockMaster.marcap)).all()
        return [{"code": r.code, "name": r.name, "market": r.market} for r in results]

    def get_aggregate_chart_data(self, category: Optional[str] = None, industry: Optional[str] = None, limit: int = 120) -> List[Dict[str, Any]]:
        """
        선택된 구분 및 업종에 속한 전체 종목들의 날짜별 평균 주가 및 전체 수급 집계/평균 데이터를 반환합니다.
        """
        q = (
            self.session.query(
                InvestorTradingDaily.date,
                func.avg(InvestorTradingDaily.close_price).label("avg_close"),
                func.avg(InvestorTradingDaily.open_price).label("avg_open"),
                func.avg(InvestorTradingDaily.high_price).label("avg_high"),
                func.avg(InvestorTradingDaily.low_price).label("avg_low"),
                func.sum(InvestorTradingDaily.volume).label("sum_volume"),
                func.sum(InvestorTradingDaily.foreigner_net_buy).label("sum_foreign"),
                func.sum(InvestorTradingDaily.institution_net_buy).label("sum_institution"),
                func.sum(InvestorTradingDaily.pension_net_buy).label("sum_pension"),
                func.sum(InvestorTradingDaily.personal_net_buy).label("sum_individual"),
            )
            .join(AllStockMaster, InvestorTradingDaily.symbol == AllStockMaster.code)
        )
        if category and category != "ALL":
            q = q.filter(or_(AllStockMaster.sector == category, AllStockMaster.market == category))
        if industry and industry != "ALL":
            q = q.filter(AllStockMaster.industry == industry)

        records = q.group_by(InvestorTradingDaily.date).order_by(desc(InvestorTradingDaily.date)).limit(limit).all()
        records.reverse()

        return [
            {
                "date": r.date,
                "open": float(r.avg_open or 0),
                "high": float(r.avg_high or 0),
                "low": float(r.avg_low or 0),
                "close": float(r.avg_close or 0),
                "volume": int(r.sum_volume or 0),
                "net_foreign": float(r.sum_foreign or 0),
                "net_institution": float(r.sum_institution or 0),
                "net_pension": float(r.sum_pension or 0),
                "net_individual": float(r.sum_individual or 0),
            }
            for r in records
        ]

    def get_stock_chart_data(self, stock_code: str, limit: int = 120) -> List[Dict[str, Any]]:
        """해당 종목의 최신 OHLCV 및 4대 주체 수급을 날짜 오름차순으로 조회하고 백엔드 퀀트 전략 시그널을 연동합니다."""
        records = (
            self.session.query(InvestorTradingDaily)
            .filter(InvestorTradingDaily.symbol == stock_code)
            .order_by(desc(InvestorTradingDaily.date))
            .limit(limit)
            .all()
        )
        records.reverse()

        res_list = [
            {
                "symbol": r.symbol,
                "date": r.date,
                "open": float(r.open_price or 0),
                "high": float(r.high_price or 0),
                "low": float(r.low_price or 0),
                "close": float(r.close_price or 0),
                "volume": int(r.volume or 0),
                "net_foreign": float(r.foreigner_net_buy or 0),
                "net_institution": float(r.institution_net_buy or 0),
                "net_pension": float(r.pension_net_buy or 0),
                "net_individual": float(r.personal_net_buy or 0),
                "open_price": float(r.open_price or 0),
                "high_price": float(r.high_price or 0),
                "low_price": float(r.low_price or 0),
                "close_price": float(r.close_price or 0),
                "foreigner_net_buy": float(r.foreigner_net_buy or 0),
                "institution_net_buy": float(r.institution_net_buy or 0),
                "pension_net_buy": float(r.pension_net_buy or 0),
                "personal_net_buy": float(r.personal_net_buy or 0),
                "s1c_signal": None,
            }
            for r in records
        ]

        if res_list:
            try:
                df = pd.DataFrame(res_list)
                if "symbol" not in df.columns or df["symbol"].isnull().any():
                    df["symbol"] = stock_code
                if "close_price" not in df.columns:
                    df["close_price"] = df["close"]

                # 오직 backend/app/services/strategies 전략 엔진 모듈에서만 시그널을 수신
                strategy = S1cMACrossAdaptiveStrategy()
                df_strat = strategy.calculate_indicators(df)

                signal_map = {}
                for _, row in df_strat.iterrows():
                    d_key = str(row["date"])
                    b_sig = bool(row.get("signal_buy", False)) if "signal_buy" in df_strat.columns else False
                    s_sig = bool(row.get("signal_sell", False)) if "signal_sell" in df_strat.columns else False
                    signal_map[d_key] = "BUY" if b_sig else ("SELL" if s_sig else None)

                for r_dict in res_list:
                    d_key = str(r_dict["date"])
                    r_dict["s1c_signal"] = signal_map.get(d_key, None)
            except Exception as e:
                logger.error(f"S1c 전략 시그널 연산 중 예외 발생: {e}", exc_info=True)
                for r_dict in res_list:
                    r_dict["s1c_signal"] = None

        return res_list

    def get_top_investor_trading(self, target_date: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
        """최신 거래일자 기준 외국인/기관/연기금 순매수 상위 TOP 20 종목을 조회합니다."""
        if not target_date:
            latest_rec = self.session.query(InvestorTradingDaily.date).order_by(desc(InvestorTradingDaily.date)).first()
            target_date = latest_rec[0] if latest_rec else ""

        if not target_date:
            return {"date": "", "foreign": [], "institution": [], "pension": []}

        foreign_top = (
            self.session.query(InvestorTradingDaily, AllStockMaster.name)
            .outerjoin(AllStockMaster, InvestorTradingDaily.symbol == AllStockMaster.code)
            .filter(InvestorTradingDaily.date == target_date)
            .order_by(desc(InvestorTradingDaily.foreigner_net_buy))
            .limit(limit)
            .all()
        )

        inst_top = (
            self.session.query(InvestorTradingDaily, AllStockMaster.name)
            .outerjoin(AllStockMaster, InvestorTradingDaily.symbol == AllStockMaster.code)
            .filter(InvestorTradingDaily.date == target_date)
            .order_by(desc(InvestorTradingDaily.institution_net_buy))
            .limit(limit)
            .all()
        )

        pension_top = (
            self.session.query(InvestorTradingDaily, AllStockMaster.name)
            .outerjoin(AllStockMaster, InvestorTradingDaily.symbol == AllStockMaster.code)
            .filter(InvestorTradingDaily.date == target_date)
            .order_by(desc(InvestorTradingDaily.pension_net_buy))
            .limit(limit)
            .all()
        )

        def format_item(row):
            rec, name = row
            return {
                "code": rec.symbol,
                "name": name or rec.symbol,
                "close": float(rec.close_price or 0),
                "change_rate": 0.0,
                "net_foreign": float(rec.foreigner_net_buy or 0),
                "net_institution": float(rec.institution_net_buy or 0),
                "net_pension": float(rec.pension_net_buy or 0),
            }

        return {
            "date": target_date,
            "foreign": [format_item(r) for r in foreign_top],
            "institution": [format_item(r) for r in inst_top],
            "pension": [format_item(r) for r in pension_top],
        }

    def get_market_indices_summary(self) -> Dict[str, Any]:
        """헤더 상단 요약 정보 칩 및 주요 지수를 반환합니다."""
        total_stocks = self.session.query(func.count(TargetStocks.symbol)).scalar() or 0
        total_records = self.session.query(func.count(InvestorTradingDaily.symbol)).scalar() or 0
        latest_date_rec = self.session.query(InvestorTradingDaily.date).order_by(desc(InvestorTradingDaily.date)).first()
        latest_date = latest_date_rec[0] if latest_date_rec else "-"

        latest_sync = self.session.query(SyncLogs).order_by(desc(SyncLogs.created_at)).first()
        if latest_sync and latest_sync.created_at:
            last_sync_time = latest_sync.created_at.strftime("%Y-%m-%d %H:%M:%S")
        else:
            last_sync_time = "-"

        latest_indices = (
            self.session.query(MarketIndicesDaily)
            .order_by(desc(MarketIndicesDaily.date))
            .limit(10)
            .all()
        )

        formatted_indices = []
        for idx in latest_indices:
            formatted_indices.append({"date": idx.date, "index_name": "KOSPI", "close": float(idx.kospi_close or 0), "change_rate": 0.0})
            formatted_indices.append({"date": idx.date, "index_name": "KOSDAQ", "close": float(idx.kosdaq_close or 0), "change_rate": 0.0})

        return {
            "total_stocks": total_stocks,
            "total_records": total_records,
            "latest_date": latest_date,
            "last_sync_time": last_sync_time,
            "indices": formatted_indices
        }
