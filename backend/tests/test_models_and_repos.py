"""
ORM 모델 및 Repository 데이터베이스 입출력 검증 모듈.

inspect 모듈을 활용하여 fixture 입력 파라미터 완전성을 자동 Assert 검증하고,
[입력값 | 예상값 | 실제 실행 결과]를 터미널에 대조 출력합니다.
"""

import os
import json
import inspect
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.core.database import Base
from backend.app.repositories.stock_master_repository import StockMasterRepository
from backend.app.repositories.market_data_repository import MarketDataRepository

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "test_collector_data.json")


class TestModelsAndRepos(unittest.TestCase):
    """
    ORM 및 Repository 기능 검증 테스트 클래스.
    """

    def setUp(self) -> None:
        """인메모리 SQLite 테스트 세션 생성."""
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

        with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
            self.fixtures = json.load(f)

    def tearDown(self) -> None:
        """테스트 세션 정리."""
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

    def test_stock_master_bulk_upsert(self) -> None:
        """StockMasterRepository bulk_upsert 테스트."""
        cases = self.fixtures["test_stock_master_upsert"]
        repo = StockMasterRepository(self.session)

        for case in cases:
            inp = case["input"]
            exp = case["expected"]
            self.assert_parameters_complete(repo.bulk_upsert, inp)

            res = repo.bulk_upsert(inp["items"])
            print(f"\n[입력값: {inp} | 예상값: {exp['saved_count']} | 실제 결과: {res}]")
            self.assertEqual(res, exp["saved_count"])

    def test_market_data_bulk_upsert(self) -> None:
        """MarketDataRepository bulk_upsert 테스트."""
        cases = self.fixtures["test_market_data_upsert"]
        repo = MarketDataRepository(self.session)

        for case in cases:
            inp = case["input"]
            exp = case["expected"]
            self.assert_parameters_complete(repo.bulk_upsert, inp)

            res = repo.bulk_upsert(inp["items"])
            print(f"\n[입력값: {inp} | 예상값: {exp['saved_count']} | 실제 결과: {res}]")
            self.assertEqual(res, exp["saved_count"])


if __name__ == "__main__":
    unittest.main()
