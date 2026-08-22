"""
[06번 테스트] run_data_collection.py 통합 수집 실행 파이프라인 검증 모듈.

inspect 모듈을 활용하여 입력 파라미터 완전성을 자동 Assert 검증하고
[입력값 | 예상값 | 실제 실행 결과]를 1:1 대조 출력하는 Test06RunDataCollection 클래스를 정의합니다.
"""

import os
import json
import inspect
import unittest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.core.database import Base
from run_data_collection import run_pipeline

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "test_06_run_data_collection_data.json")


class Test06RunDataCollection(unittest.TestCase):
    """
    06번 테스트: run_data_collection.py 파이프라인 실행 입출력 대조 검증 클래스.
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

    def test_01_run_pipeline_incremental(self) -> None:
        """[6-1번 테스트] run_pipeline 스마트 증분 수집 모드(incremental) 검증."""
        data = self.fixtures["test_01_run_pipeline_incremental"]
        inp = data["input"]
        self.assert_parameters_complete(run_pipeline, inp)

        mock_stage1 = {"total_fetched": 1, "master_saved": 1, "targets_saved": 1}
        mock_stage2 = {"fetched_count": 1, "saved_count": 1, "skipped": False}
        mock_stage3 = {"target_symbols_count": 1, "total_records_saved": 1, "skipped_symbols_count": 0, "log_id": 1}

        with patch("run_data_collection.StockMasterCollector") as MockMaster, \
             patch("run_data_collection.MarketIndicesCollector") as MockIndices, \
             patch("run_data_collection.MarketDataCollector") as MockMarketData:

            MockMaster.return_value.run_sync.return_value = mock_stage1
            MockIndices.return_value.collect_market_indices.return_value = mock_stage2
            MockMarketData.return_value.collect_target_market_data.return_value = mock_stage3

            # 파이프라인 실행
            run_pipeline(mode=inp["mode"], stage=inp.get("stage", "all"), start_date=inp["start_date"], end_date=inp["end_date"])
            actual_status = "SUCCESS"
            print(f"\n[run_pipeline(incremental) | 입력값: {inp} | 예상상태: {data['expected']['status']} | 실제: {actual_status}]")
            self.assertEqual(actual_status, data["expected"]["status"])

    def test_02_run_pipeline_full(self) -> None:
        """[6-2번 테스트] run_pipeline 전체 수집 모드(full) 검증."""
        data = self.fixtures["test_02_run_pipeline_full"]
        inp = data["input"]
        self.assert_parameters_complete(run_pipeline, inp)

        mock_stage1 = {"total_fetched": 1, "master_saved": 1, "targets_saved": 1}
        mock_stage2 = {"fetched_count": 1, "saved_count": 1, "skipped": False}
        mock_stage3 = {"target_symbols_count": 1, "total_records_saved": 1, "skipped_symbols_count": 0, "log_id": 1}

        with patch("run_data_collection.StockMasterCollector") as MockMaster, \
             patch("run_data_collection.MarketIndicesCollector") as MockIndices, \
             patch("run_data_collection.MarketDataCollector") as MockMarketData:

            MockMaster.return_value.run_sync.return_value = mock_stage1
            MockIndices.return_value.collect_market_indices.return_value = mock_stage2
            MockMarketData.return_value.collect_target_market_data.return_value = mock_stage3

            # 파이프라인 실행
            run_pipeline(mode=inp["mode"], stage=inp.get("stage", "all"), start_date=inp["start_date"], end_date=inp["end_date"])
            actual_status = "SUCCESS"
            print(f"[run_pipeline(full) | 입력값: {inp} | 예상상태: {data['expected']['status']} | 실제: {actual_status}]")
            self.assertEqual(actual_status, data["expected"]["status"])

    def test_03_run_pipeline_stage1(self) -> None:
        """[6-3번 테스트] run_pipeline 1단계 단독 실행 검증."""
        data = self.fixtures["test_03_run_pipeline_stage1"]
        inp = data["input"]
        self.assert_parameters_complete(run_pipeline, inp)

        mock_stage1 = {"total_fetched": 1, "master_saved": 1, "targets_saved": 1}

        with patch("run_data_collection.StockMasterCollector") as MockMaster, \
             patch("run_data_collection.MarketIndicesCollector") as MockIndices, \
             patch("run_data_collection.MarketDataCollector") as MockMarketData:

            MockMaster.return_value.run_sync.return_value = mock_stage1

            run_pipeline(mode=inp["mode"], stage=inp.get("stage", "1"), start_date=inp["start_date"], end_date=inp["end_date"])
            actual_status = "SUCCESS"
            print(f"[run_pipeline(stage1) | 입력값: {inp} | 예상상태: {data['expected']['status']} | 실제: {actual_status}]")
            self.assertEqual(actual_status, data["expected"]["status"])
            # 1단계만 실행되었으므로 2, 3단계 Collector는 호출되지 않음
            MockIndices.return_value.collect_market_indices.assert_not_called()
            MockMarketData.return_value.collect_target_market_data.assert_not_called()


if __name__ == "__main__":
    unittest.main()
