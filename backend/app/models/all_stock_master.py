"""
전 증시 종목 마스터 ORM 모델 모듈.

국내 전 증시(KOSPI, KOSDAQ, ETF 등)의 종목 기본 정보를
저장 및 관리하는 테이블과 매칭되는 AllStockMaster 클래스를 정의합니다.
"""

from datetime import datetime
from sqlalchemy import Column, String, BigInteger, DateTime
from backend.app.core.database import Base


class AllStockMaster(Base):
    """
    전 증시 종목 마스터 ORM 모델 클래스.
    """
    __tablename__ = "all_stock_master"

    # 종목코드 (예: 005930) - Primary Key
    code = Column(String(20), primary_key=True, comment="종목코드")
    # 종목명 (예: 삼성전자)
    name = Column(String(100), nullable=False, index=True, comment="종목명")
    # 시장구분 (KOSPI / KOSDAQ / ETF 등)
    market = Column(String(20), nullable=False, index=True, comment="시장구분")
    # 세부 산업분류 (예: 반도체와반도체장비, IT 서비스, 자동차부품 등)
    industry = Column(String(100), nullable=True, index=True, comment="세부 산업분류")
    # 지수구분 (KOSPI 200 / KOSDAQ 150 / ETF_USA / 일반)
    sector = Column(String(100), nullable=True, index=True, comment="지수구분")
    # 시가총액 (원)
    marcap = Column(BigInteger, nullable=True, comment="시가총액(원)")
    # 상장주식수
    stocks = Column(BigInteger, nullable=True, comment="상장주식수")
    # 등록 일시
    created_at = Column(DateTime, default=datetime.utcnow, comment="등록일시")
    # 수정 일시
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="수정일시")

    def __repr__(self) -> str:
        """AllStockMaster 객체의 문자열 표현을 반환합니다."""
        return f"<AllStockMaster(code='{self.code}', name='{self.name}', market='{self.market}')>"
