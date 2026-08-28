"""투자제안 어드바이저 인스턴스 공유 캐시 모듈 (proposal_advisor_cache.py).

기준일 + 수급 데이터 최신일자별로 '로딩·지표 연산이 끝난' ProposalAdvisor 1개를
프로세스 전역에서 공유·재사용하여, 투자제안 화면의 두 API(/recommended-stocks,
/paper-trading/portfolio) 및 '당일 조회' 반복 호출이 같은 연산 결과를 나눠 쓰도록 한다.
"""

import threading
from typing import Dict, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.models.investor_trading_daily import InvestorTradingDaily
from backend.app.services.proposal_advisor import ProposalAdvisor


class ProposalAdvisorCache:
    """(기준일, 데이터 최신일) 키로 로딩 완료 ProposalAdvisor를 공유하는 프로세스 캐시."""

    _MAX_ENTRIES = 4               # 최근 기준일 몇 개까지만 유지 (LRU 유사)
    _lock = threading.Lock()
    _store: Dict[Tuple[str, str], ProposalAdvisor] = {}

    @classmethod
    def data_version(cls, session: Session) -> str:
        """수급 데이터의 최신 일자를 반환한다. 동기화로 값이 바뀌면 캐시가 무효화된다.

        :param session: SQLAlchemy DB 세션
        :return: investor_trading_daily.date 최대값(YYYYMMDD). 데이터 없으면 빈 문자열.
        """
        latest = session.query(func.max(InvestorTradingDaily.date)).scalar()
        return latest or ""

    @classmethod
    def get(cls, session: Session, target_date: str) -> ProposalAdvisor:
        """기준일에 대응하는 '로딩 완료' ProposalAdvisor를 반환한다(없으면 생성·캐싱).

        캐시 히트 시 반환되는 인스턴스는 이미 시세 로딩이 끝나 있어, 이후
        get_recommendations()/build_portfolio_view() 호출이 DB 세션을 사용하지 않는다.

        :param session: 현재 요청의 DB 세션 (버전 조회 및 최초 로딩에만 사용)
        :param target_date: 추천/평가 기준일 (YYYYMMDD)
        :return: _load(target_date)가 완료된 ProposalAdvisor
        """
        key = (target_date, cls.data_version(session))
        with cls._lock:
            advisor = cls._store.get(key)
            if advisor is None:
                advisor = ProposalAdvisor(session)
                advisor.load(target_date)
                cls._store[key] = advisor
                # 오래된 항목부터 제거하여 캐시 크기 제한
                while len(cls._store) > cls._MAX_ENTRIES:
                    cls._store.pop(next(iter(cls._store)))
            return advisor
