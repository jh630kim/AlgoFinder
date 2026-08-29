"""
모의투자 및 투자제안 자산 관리 DB 모델 (paper_trading.py).

모의투자(account_type='rec')와 투자제안(account_type='prop')의 자산 계좌 및 체결 이력을
독립적으로 완전 분리하여 관리하는 SQLAlchemy ORM 클래스를 정의합니다.
"""

from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, DateTime
from backend.app.core.database import Base


class PaperPortfolio(Base):
    """
    자산 계좌 상태 ORM 모델 클래스 (계좌유형별 분리).
    """
    __tablename__ = "paper_portfolios"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="자산 계좌 식별 ID")
    account_type = Column(String(20), default="rec", nullable=False, index=True, comment="계좌 유형 (rec: 모의투자, prop: 투자제안)")
    initial_balance = Column(Float, default=10000000.0, nullable=False, comment="초기 투자 자산 (원)")
    cash_balance = Column(Float, default=10000000.0, nullable=False, comment="현재 잔여 현금 (원)")
    total_asset_value = Column(Float, default=10000000.0, nullable=False, comment="총 자산 평가액 (원)")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="최종 업데이트 일시")

    def to_dict(self) -> dict:
        """자산 계좌 정보를 딕셔너리로 변환합니다."""
        return {
            "id": self.id,
            "account_type": self.account_type,
            "initial_balance": self.initial_balance,
            "cash_balance": self.cash_balance,
            "total_asset_value": self.total_asset_value,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None,
        }


class PaperPosition(Base):
    """
    보유 종목 잔고 ORM 모델 클래스 (계좌유형별 분리).
    """
    __tablename__ = "paper_positions"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="포지션 ID")
    account_type = Column(String(20), default="rec", nullable=False, index=True, comment="계좌 유형 (rec: 모의투자, prop: 투자제안)")
    stock_code = Column(String(20), nullable=False, index=True, comment="종목 코드")
    stock_name = Column(String(100), nullable=False, comment="종목명")
    buy_date = Column(String(10), nullable=False, comment="매수일 (YYYY-MM-DD)")
    buy_price = Column(Float, nullable=False, comment="매수가 (당일 종가)")
    quantity = Column(Integer, nullable=False, comment="보유 수량")
    total_amount = Column(Float, nullable=False, comment="총 투입 금액 (원)")
    entry_strategy = Column(String(20), nullable=True, comment="개시 전략 태그 (S1~S5 / 순수관행 / MANUAL)")
    created_at = Column(DateTime, default=datetime.now, comment="생성 일시")

    def to_dict(self) -> dict:
        """보유 종목 잔고 정보를 딕셔너리로 변환합니다."""
        return {
            "id": self.id,
            "account_type": self.account_type,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "buy_date": self.buy_date,
            "buy_price": self.buy_price,
            "quantity": self.quantity,
            "total_amount": self.total_amount,
            "entry_strategy": self.entry_strategy,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }


class PaperTradeHistory(Base):
    """
    가상 매수/매도 체결 로그 ORM 모델 클래스 (계좌유형별 분리).
    """
    __tablename__ = "paper_trade_histories"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="체결 로그 ID")
    account_type = Column(String(20), default="rec", nullable=False, index=True, comment="계좌 유형 (rec: 모의투자, prop: 투자제안)")
    trade_date = Column(String(10), nullable=False, comment="체결 일자 (YYYY-MM-DD)")
    trade_type = Column(String(20), nullable=False, comment="체결 유형 (BUY / SELL / MANUAL_BUY)")
    stock_code = Column(String(20), nullable=False, comment="종목 코드")
    stock_name = Column(String(100), nullable=False, comment="종목명")
    price = Column(Float, nullable=False, comment="체결 단가 (원)")
    quantity = Column(Integer, nullable=False, comment="체결 수량")
    total_amount = Column(Float, nullable=False, comment="총 체결 금액")
    realized_pnl = Column(Float, default=0.0, comment="실현 손익금 (원)")
    entry_strategy = Column(String(20), nullable=True, comment="개시 전략 태그 (매수행)")
    created_at = Column(DateTime, default=datetime.now, comment="생성 일시")

    def to_dict(self) -> dict:
        """체결 로그 정보를 딕셔너리로 변환합니다."""
        return {
            "id": self.id,
            "account_type": self.account_type,
            "trade_date": self.trade_date,
            "trade_type": self.trade_type,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "price": self.price,
            "quantity": self.quantity,
            "total_amount": self.total_amount,
            "realized_pnl": self.realized_pnl,
            "entry_strategy": self.entry_strategy,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }
