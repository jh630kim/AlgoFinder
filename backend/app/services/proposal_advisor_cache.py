"""투자제안 어드바이저 인스턴스 공유 캐시 모듈 (proposal_advisor_cache.py).

(모드, 수급 데이터 최신일자) 키로 '넓은 창을 로드·지표 연산까지 끝낸' ProposalAdvisor 1개를
프로세스 전역에서 공유·재사용하여, 투자제안/모의투자 화면의 두 API(/recommended-stocks,
/paper-trading/portfolio) 및 '당일/다음날 조회' 반복 호출이 같은 연산 결과를 나눠 쓰도록 한다.
기준일 이동은 캐시된 어드바이저가 내부에서 창 슬라이스/필요 시 재적재로 처리한다.
"""

import threading
from typing import Dict, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.models.investor_trading_daily import InvestorTradingDaily
from backend.app.services.proposal_advisor import ProposalAdvisor


class ProposalAdvisorCache:
    """(모드, 데이터 최신일) 키로 로딩 완료 ProposalAdvisor를 공유하는 프로세스 캐시."""

    _MAX_ENTRIES = 4               # (모드, 데이터버전)별 항목 유지 (LRU 유사)
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
    def get(cls, session: Session, target_date: str, mode: str = "advice") -> ProposalAdvisor:
        """모드+데이터버전에 대응하는 ProposalAdvisor를 반환한다(없으면 생성·캐싱).

        반환 인스턴스는 넓은 창을 이미 로드·연산해 두었고, 넘어온 기준일이 창 안이면
        추가 DB 조회 없이 필터만 수행한다. 창 밖이면 인스턴스가 자체적으로 재적재한다.

        :param session: 현재 요청의 DB 세션 (버전 조회 및 창 적재에만 사용)
        :param target_date: 추천/평가 기준일 (YYYYMMDD) — 최초 창 적재 위치 지정용
        :param mode: "advice"(투자제안) 또는 "sim"(모의투자, D-1 신호). 캐시 키에 포함되어 상호 격리
        :return: 기준일 창이 로드된 ProposalAdvisor
        """
        key = (mode, cls.data_version(session))
        with cls._lock:
            advisor = cls._store.get(key)
            if advisor is None:
                advisor = ProposalAdvisor(session, mode)
                cls._store[key] = advisor
                # 오래된 항목부터 제거하여 캐시 크기 제한
                while len(cls._store) > cls._MAX_ENTRIES:
                    cls._store.pop(next(iter(cls._store)))
            advisor.load(target_date)
            return advisor
