"""
[03번 테스트] StockMasterCollector 서비스 객체 전수 검증 모듈.

inspect 모듈을 활용하여 입력 파라미터 완전성을 자동 Assert 검증하고
[입력값 | 예상값 | 실제 실행 결과]를 1:1 대조 출력하는 Test03StockMasterCollector 클래스를 정의합니다.
"""

import os
import json
import inspect
import unittest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.core.database import Base
from backend.app.services.stock_master_collector import StockMasterCollector

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "test_03_stock_master_collector_data.json")


class Test03StockMasterCollector(unittest.TestCase):
    """
    03번 테스트: StockMasterCollector 전용 3개 메서드 입출력 대조 검증 클래스.
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

    def test_01_fetch_master_dataframe(self) -> None:
        """[3-1번 테스트] fetch_master_dataframe 수집 메서드 검증."""
        data = self.fixtures["test_01_fetch_master_dataframe"]
        collector = StockMasterCollector(self.session)
        self.assert_parameters_complete(collector.fetch_master_dataframe, data["input"])

        # FDR StockListing 모킹 테스트
        mock_df = MagicMock()
        mock_df.iterrows.return_value = [
            (0, {"Code": "005930", "Name": "삼성전자", "Market": "KOSPI", "Sector": "KOSPI 200", "Marcap": 400000000000000, "Stocks": 5969782550})
        ]
        with patch("FinanceDataReader.StockListing", return_value=mock_df):
            result = collector.fetch_master_dataframe(data["input"]["market_code"])
            print(f"\n[StockMasterCollector.fetch_master_dataframe | 입력값: {data['input']} | 최소예상건수: {data['expected']['min_count']} | 실제건수: {len(result)}]")
            self.assertGreaterEqual(len(result), data["expected"]["min_count"])

    def test_02_filter_target_symbols(self) -> None:
        """[3-2번 테스트] filter_target_symbols 필터링 로직 검증."""
        data = self.fixtures["test_02_filter_target_symbols"]
        collector = StockMasterCollector(self.session)
        self.assert_parameters_complete(collector.filter_target_symbols, data["input"])

        res = collector.filter_target_symbols(data["input"]["items"])
        print(f"[StockMasterCollector.filter_target_symbols | 입력값: {data['input']} | 예상목록: {data['expected']['target_symbols']} | 실제: {res}]")
        self.assertEqual(res, data["expected"]["target_symbols"])

    def test_03_run_sync(self) -> None:
        """[3-3번 테스트] run_sync 동기화 파이프라인 검증."""
        data = self.fixtures["test_03_run_sync"]
        collector = StockMasterCollector(self.session)
        self.assert_parameters_complete(collector.run_sync, data["input"])

        mock_items = [
            {"code": "005930", "name": "삼성전자", "market": "KOSPI", "sector": "KOSPI 200"}
        ]
        with patch.object(collector, "fetch_master_dataframe", return_value=mock_items):
            res = collector.run_sync()
            print(f"[StockMasterCollector.run_sync | 입력값: {data['input']} | 예상: dict 반환 | 실제: {res}]")
            self.assertIsInstance(res, dict)
            self.assertIn("total_fetched", res)


if __name__ == "__main__":
    unittest.main()
