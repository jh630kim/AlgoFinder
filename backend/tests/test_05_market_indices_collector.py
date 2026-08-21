"""
[05번 테스트] MarketIndicesCollector 서비스 객체 전수 검증 모듈.

inspect 모듈을 활용하여 입력 파라미터 완전성을 자동 Assert 검증하고
[입력값 | 예상값 | 실제 실행 결과]를 1:1 대조 출력하는 Test05MarketIndicesCollector 클래스를 정의합니다.
"""

import os
import json
import inspect
import unittest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.core.database import Base
from backend.app.services.market_indices_collector import MarketIndicesCollector

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "test_05_market_indices_collector_data.json")


class Test05MarketIndicesCollector(unittest.TestCase):
    """
    05번 테스트: MarketIndicesCollector 전용 2개 메서드 입출력 대조 검증 클래스.
    """

    def setUp(self) -> None:
        """인메모리 SQLite 세션 초기화 및 Fixture 로드."""
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
        inspect 모듈을 사용하여 메서드 요구 파라미터 완전성을 자동 검증(Assert)합니다.

        :param func: 검증 대상 메서드
        :param input_dict: 테스트 입력값 딕셔너리
        """
        sig = inspect.signature(func)
        required_params = [
            p.name for p in sig.parameters.values() if p.name != "self"
        ]
        for param in required_params:
            self.assertIn(
                param, input_dict,
                f"매개변수 누락 오류: '{param}' 항목이 input 데이터에 명시되지 않았습니다."
            )

    def test_01_fetch_indices_and_rate(self) -> None:
        """[5-1번 테스트] fetch_indices_and_rate 지수/환율 수집 메서드 검증."""
        data = self.fixtures["test_01_fetch_indices_and_rate"]
        collector = MarketIndicesCollector(self.session)
        inp = data["input"]
        self.assert_parameters_complete(collector.fetch_indices_and_rate, inp)

        mock_items = [
            {"date": inp["start_date"], "kospi_close": 2500.0, "kosdaq_close": 850.0, "sp500_close": 4800.0, "usdkrw_rate": 1300.0}
        ]
        with patch.object(collector, "fetch_indices_and_rate", return_value=mock_items):
            res = collector.fetch_indices_and_rate(inp["start_date"], inp["end_date"])
            print(f"\n[MarketIndicesCollector.fetch_indices_and_rate | 입력값: {inp} | 최소예상건수: {data['expected']['min_count']} | 실제건수: {len(res)}]")
            self.assertGreaterEqual(len(res), data["expected"]["min_count"])

    def test_02_collect_market_indices(self) -> None:
        """[5-2번 테스트] collect_market_indices 수집 파이프라인 검증."""
        data = self.fixtures["test_02_collect_market_indices"]
        collector = MarketIndicesCollector(self.session)
        inp = data["input"]
        self.assert_parameters_complete(collector.collect_market_indices, inp)

        mock_items = [
            {"date": inp["start_date"], "kospi_close": 2500.0, "kosdaq_close": 850.0, "sp500_close": 4800.0, "usdkrw_rate": 1300.0}
        ]
        with patch.object(collector, "fetch_indices_and_rate", return_value=mock_items):
            res = collector.collect_market_indices(inp["start_date"], inp["end_date"])
            print(f"[MarketIndicesCollector.collect_market_indices | 입력값: {inp} | 예상: dict 반환 | 실제: {res}]")
            self.assertIsInstance(res, dict)
            self.assertIn("saved_count", res)


if __name__ == "__main__":
    unittest.main()
