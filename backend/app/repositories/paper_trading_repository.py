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
        buy_date: str, buy_price: float, quantity: int
    ) -> PaperPosition:
        """지정된 계좌 유형에 신규 보유 잔고를 생성합니다."""
        position = PaperPosition(
            account_type=account_type, stock_code=stock_code, stock_name=stock_name,
            buy_date=buy_date, buy_price=float(buy_price), quantity=int(quantity),
            total_amount=float(buy_price) * int(quantity)
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

    def add_trade_history(
        self,
        account_type: str,
        trade_date: str,
        trade_type: str,
        stock_code: str,
        stock_name: str,
        price: float,
        quantity: int,
        realized_pnl: float = 0.0
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
            created_at=datetime.now()
        )
        self.session.add(history)
        self.session.commit()
        return history
