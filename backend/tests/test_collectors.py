"""
수집기 파이프라인(StockMasterCollector) 검증 모듈.

inspect 모듈을 활용하여 입력 파라미터 완전성을 자동 검증하고,
[입력값 | 예상값 | 실제 실행 결과] 대조 출력을 전담하는 TestCollectors 클래스를 정의합니다.
"""

import os
import json
import inspect
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.core.database import Base
from backend.app.services.stock_master_collector import StockMasterCollector

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "test_collector_data.json")


class TestCollectors(unittest.TestCase):
    """
    수집기 서비스 클래스 기능 검증 단위 테스트.
    """

    def setUp(self) -> None:
        """인메모리 SQLite 세션 초기화."""
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

        with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
            self.fixtures = json.load(f)

    def tearDown(self) -> None:
        """테스트 세션 종료."""
        self.session.close()

    def assert_parameters_complete(self, func, input_dict: dict) -> None:
        """
        inspect 모듈을 사용하여 함수 매개변수 완전성을 자동 검증(Assert)합니다.

        :param func: 검증 대상 메서드
        :param input_dict: 테스트 입력값 딕셔너리
        """
        sig = inspect.signature(func)
        required_params = [
            p.name for p in sig.parameters.values()
            if p.name != "self"
        ]
        for param in required_params:
            self.assertIn(
                param, input_dict,
                f"매개변수 누락 오류: '{param}' 항목이 input 데이터에 명시되지 않았습니다."
            )

    def test_filter_target_symbols(self) -> None:
        """StockMasterCollector의 타깃 필터링 로직 검증."""
        cases = self.fixtures["test_target_symbols_filter"]
        collector = StockMasterCollector(self.session)

        for case in cases:
            inp = case["input"]
            exp = case["expected"]
            self.assert_parameters_complete(collector.filter_target_symbols, inp)

            res = collector.filter_target_symbols(inp["items"])
            print(f"\n[입력값: {inp} | 예상값: {exp['target_symbols']} | 실제 결과: {res}]")
            self.assertEqual(res, exp["target_symbols"])


if __name__ == "__main__":
    unittest.main()
