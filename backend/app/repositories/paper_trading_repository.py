"""
모의투자 및 투자제안 자산 관리 전용 레포지토리 (paper_trading_repository.py).

계좌 유형(account_type='rec' 또는 'prop')별로 독립적인 자산 및 거래 이력 DB 접근 쿼리를 수행합니다.
"""

from typing import List
from datetime import datetime
from sqlalchemy.orm import Session
from backend.app.models.paper_trading import PaperPortfolio, PaperPosition, PaperTradeHistory


class PaperTradingRepository:
    """모의투자/투자제안 분리 자산 DB 레포지토리 클래스."""

    def __init__(self, session: Session):
        """DB 세션을 초기화합니다."""
        self.session = session

    def get_or_create_portfolio(self, account_type: str = "rec") -> PaperPortfolio:
        """지정된 계좌 유형(rec 또는 prop)의 기존 자산 계좌를 조회하거나 새로 생성합니다."""
        portfolio = self.session.query(PaperPortfolio).filter(PaperPortfolio.account_type == account_type).first()
        if not portfolio:
            portfolio = PaperPortfolio(
                account_type=account_type,
                initial_balance=10000000.0,
                cash_balance=10000000.0,
                total_asset_value=10000000.0,
                updated_at=datetime.now()
            )
            self.session.add(portfolio)
            self.session.commit()
            self.session.refresh(portfolio)
        return portfolio

    def reset_portfolio(self, account_type: str = "rec", initial_balance: float = 10000000.0) -> PaperPortfolio:
        """지정된 계좌 유형의 자산을 독립 초기화하고 해당 계좌 보유 잔고를 삭제합니다."""
        self.session.query(PaperPosition).filter(PaperPosition.account_type == account_type).delete()
        portfolio = self.get_or_create_portfolio(account_type)
        portfolio.initial_balance = float(initial_balance)
        portfolio.cash_balance = float(initial_balance)
        portfolio.total_asset_value = float(initial_balance)
        portfolio.updated_at = datetime.now()
        self.session.commit()
        self.session.refresh(portfolio)
        return portfolio

    def get_positions(self, account_type: str = "rec") -> List[PaperPosition]:
        """지정된 계좌 유형의 현재 보유 중인 종목 잔고 리스트를 조회합니다."""
        return self.session.query(PaperPosition).filter(PaperPosition.account_type == account_type).all()

    def get_position(self, account_type: str, stock_code: str) -> PaperPosition:
        """지정된 계좌 유형에서 특정 종목의 보유 잔고를 조회합니다(없으면 None)."""
        return self.session.query(PaperPosition).filter(
            PaperPosition.account_type == account_type,
            PaperPosition.stock_code == stock_code
        ).first()

    def add_position(
        self, account_type: str, stock_code: str, stock_name: str,
        buy_date: str, buy_price: float, quantity: int, entry_strategy: str = None
    ) -> PaperPosition:
        """지정된 계좌 유형에 신규 보유 잔고를 생성합니다.

        :param entry_strategy: 개시 전략 태그(S1~S5 / 순수관행 / MANUAL). 매도뷰 표시용.
        """
        position = PaperPosition(
            account_type=account_type, stock_code=stock_code, stock_name=stock_name,
            buy_date=buy_date, buy_price=float(buy_price), quantity=int(quantity),
            total_amount=float(buy_price) * int(quantity), entry_strategy=entry_strategy
        )
        self.session.add(position)
        self.session.commit()
        self.session.refresh(position)
        return position

    def reduce_position(self, position: PaperPosition, sell_qty: int) -> None:
        """보유 잔고에서 매도 수량만큼 차감하고, 전량 매도 시 잔고를 삭제합니다."""
        remaining = position.quantity - int(sell_qty)
        if remaining <= 0:
            self.session.delete(position)
        else:
            position.quantity = remaining
            position.total_amount = position.buy_price * remaining
        self.session.commit()

    def export_account(self, account_type: str = "prop") -> dict:
        """계좌·보유·체결 이력을 id 없는 딕셔너리 묶음으로 반환합니다(JSON 백업용)."""
        pf = self.get_or_create_portfolio(account_type)
        positions = self.session.query(PaperPosition).filter(
            PaperPosition.account_type == account_type
        ).all()
        history = self.session.query(PaperTradeHistory).filter(
            PaperTradeHistory.account_type == account_type
        ).all()
        strip = lambda d: {k: v for k, v in d.items() if k != "id"}
        return {
            "portfolio": strip(pf.to_dict()),
            "positions": [strip(p.to_dict()) for p in positions],
            "trade_history": [strip(h.to_dict()) for h in history],
        }

    def replace_account(self, account_type: str, data: dict) -> dict:
        """계좌의 보유·체결을 모두 지우고 data로 재구성합니다(전체 교체). 반영 건수를 반환."""
        self.session.query(PaperPosition).filter(PaperPosition.account_type == account_type).delete()
        self.session.query(PaperTradeHistory).filter(PaperTradeHistory.account_type == account_type).delete()

        pf = self.get_or_create_portfolio(account_type)
        p = data.get("portfolio", {}) or {}
        pf.initial_balance = float(p.get("initial_balance", 10000000.0))
        pf.cash_balance = float(p.get("cash_balance", pf.initial_balance))
        pf.total_asset_value = float(p.get("total_asset_value", pf.cash_balance))
        pf.updated_at = datetime.now()

        for row in data.get("positions", []) or []:
            qty = int(row["quantity"])
            price = float(row["buy_price"])
            self.session.add(PaperPosition(
                account_type=account_type, stock_code=str(row["stock_code"]),
                stock_name=str(row.get("stock_name") or row["stock_code"]),
                buy_date=str(row.get("buy_date", "")), buy_price=price, quantity=qty,
                total_amount=float(row.get("total_amount", price * qty)),
            ))
        for row in data.get("trade_history", []) or []:
            self.session.add(PaperTradeHistory(
                account_type=account_type, trade_date=str(row.get("trade_date", "")),
                trade_type=str(row.get("trade_type", "")), stock_code=str(row.get("stock_code", "")),
                stock_name=str(row.get("stock_name", "")), price=float(row.get("price", 0) or 0),
                quantity=int(row.get("quantity", 0) or 0), total_amount=float(row.get("total_amount", 0) or 0),
                realized_pnl=float(row.get("realized_pnl", 0) or 0),
            ))
        self.session.commit()
        return {
            "portfolios": 1,
            "positions": len(data.get("positions", []) or []),
            "trade_history": len(data.get("trade_history", []) or []),
        }

    def add_trade_history(
        self,
        account_type: str,
        trade_date: str,
        trade_type: str,
        stock_code: str,
        stock_name: str,
        price: float,
        quantity: int,
        realized_pnl: float = 0.0,
        entry_strategy: str = None
    ) -> PaperTradeHistory:
        """지정된 계좌 유형의 가상 체결 이력 로그를 저장합니다."""
        history = PaperTradeHistory(
            account_type=account_type,
            trade_date=trade_date,
            trade_type=trade_type,
            stock_code=stock_code,
            stock_name=stock_name,
            price=price,
            quantity=quantity,
            total_amount=price * quantity,
            realized_pnl=realized_pnl,
            entry_strategy=entry_strategy,
            created_at=datetime.now()
        )
        self.session.add(history)
        self.session.commit()
        return history
