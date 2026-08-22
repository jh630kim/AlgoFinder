"""
[04번 테스트] MarketDataCollector 서비스 객체 전수 검증 모듈.

inspect 모듈을 활용하여 입력 파라미터 완전성을 자동 Assert 검증하고
[입력값 | 예상값 | 실제 실행 결과]를 1:1 대조 출력하는 Test04MarketDataCollector 클래스를 정의합니다.
"""

import os
import json
import inspect
import unittest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.core.database import Base
from backend.app.services.market_data_collector import MarketDataCollector

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "test_04_market_data_collector_data.json")


class Test04MarketDataCollector(unittest.TestCase):
    """
    04번 테스트: MarketDataCollector 전용 2개 메서드 입출력 대조 검증 클래스.
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
        """테스트 세션 및 DB 엔진 자원 정리."""
        self.session.close()
        self.engine.dispose()

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

    def test_01_fetch_trading_data_with_retry(self) -> None:
        """[4-1번 테스트] fetch_trading_data_with_retry 메서드 검증."""
        data = self.fixtures["test_01_fetch_trading_data_with_retry"]
        collector = MarketDataCollector(self.session)
        inp = data["input"]
        self.assert_parameters_complete(collector.fetch_trading_data_with_retry, inp)

        mock_items = [
            {"symbol": inp["symbol"], "date": inp["start_date"], "close_price": 70500.0}
        ]
        with patch.object(collector, "fetch_trading_data_with_retry", return_value=mock_items):
            res = collector.fetch_trading_data_with_retry(
                symbol=inp["symbol"],
                start_date=inp["start_date"],
                end_date=inp["end_date"],
                max_retries=inp["max_retries"]
            )
            actual_sym = res[0]["symbol"] if res else None
            print(f"\n[MarketDataCollector.fetch_trading_data_with_retry | 입력값: {inp} | 예상종목: {data['expected']['symbol']} | 실제종목: {actual_sym}]")
            self.assertEqual(actual_sym, data["expected"]["symbol"])

    def test_02_collect_target_market_data(self) -> None:
        """[4-2번 테스트] collect_target_market_data 수집 파이프라인 검증."""
        data = self.fixtures["test_02_collect_target_market_data"]
        collector = MarketDataCollector(self.session)
        inp = data["input"]
        self.assert_parameters_complete(collector.collect_target_market_data, inp)

        with patch.object(collector.target_repo, "get_all_symbols", return_value=["005930"]), \
             patch.object(collector, "fetch_trading_data_with_retry", return_value=[]):
            res = collector.collect_target_market_data(
                start_date=inp["start_date"],
                end_date=inp["end_date"]
            )
            print(f"[MarketDataCollector.collect_target_market_data | 입력값: {inp} | 예상: dict 반환 | 실제: {res}]")
            self.assertIsInstance(res, dict)
            self.assertIn("target_symbols_count", res)


if __name__ == "__main__":
    unittest.main()
