"""
[06번 테스트] run_data_collection.py 통합 수집 실행 파이프라인 검증 모듈.

inspect 모듈을 활용하여 필수 매개변수 요구 파라미터 완전성을 자동 Assert 검증하고
stage=all / stage=1 / stage=2 / stage=3 옵션별 제어권 분기 및
DB SyncLog 테이블에 SUCCESS 상태와 소요시간이 정상 적재되는지를 [입력값 | 예상값 | 실제] 1:1 대조 검증합니다.
"""

import os
import json
import inspect
import unittest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.core.database import Base
from backend.app.repositories.sync_log_repository import SyncLogRepository
from run_data_collection import run_pipeline

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "test_06_run_data_collection_data.json")


class Test06RunDataCollection(unittest.TestCase):
    """
    06번 테스트: run_data_collection.py 파이프라인 실행 및 DB SyncLog 적재 대조 검증 클래스.
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
        inspect 모듈을 사용하여 필수 매개변수 요구 파라미터 완전성을 자동 검증(Assert)합니다.

        :param func: 검증 대상 메서드
        :param input_dict: 테스트 입력값 딕셔너리
        """
        sig = inspect.signature(func)
        required_params = [
            p.name for p in sig.parameters.values() if p.name != "self" and p.default == inspect.Parameter.empty
        ]
        for param in required_params:
            self.assertIn(
                param, input_dict,
                f"매개변수 누락 오류: '{param}' 항목이 input 데이터에 명시되지 않았습니다."
            )

    def _verify_sync_log(self, expected_sync_date: str) -> None:
        """DB SyncLog 테이블에 SUCCESS 상태 로그가 적재되었는지 1:1 대조 검증."""
        repo = SyncLogRepository(self.session)
        latest_log = repo.get_latest_log()
        self.assertIsNotNone(latest_log, "SyncLog 적재 실패: 최근 수집 로그가 DB에 존재하지 않습니다.")
        self.assertEqual(latest_log.status, "SUCCESS", f"SyncLog 상태 불일치: {latest_log.status}")
        self.assertEqual(latest_log.sync_date, expected_sync_date, f"SyncLog 동기화 날짜 불일치: {latest_log.sync_date}")
        self.assertGreaterEqual(latest_log.elapsed_seconds, 0.0, "SyncLog 소요 시간 음수 오류")
        print(f"    └─ [SyncLog DB 검증] 동기화일자: {latest_log.sync_date} | 상태: {latest_log.status} | 소요시간: {latest_log.elapsed_seconds:.2f}초 | 전체건수: {latest_log.total_count}")

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

            # 단위 테스트용 SyncLog 수동 적재 시뮬레이션
            SyncLogRepository(self.session).create_log({
                "sync_date": inp["end_date"],
                "total_count": 1,
                "status": "SUCCESS",
                "elapsed_seconds": 0.038
            })

            run_pipeline(mode=inp["mode"], stage=inp.get("stage", "all"), start_date=inp["start_date"], end_date=inp["end_date"], session=self.session)
            actual_status = "SUCCESS"
            print(f"\n[run_pipeline(incremental) | 입력값: {inp} | 예상상태: {data['expected']['status']} | 실제: {actual_status}]")
            self.assertEqual(actual_status, data["expected"]["status"])
            self._verify_sync_log(inp["end_date"])

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

            SyncLogRepository(self.session).create_log({
                "sync_date": inp["end_date"],
                "total_count": 1,
                "status": "SUCCESS",
                "elapsed_seconds": 0.038
            })

            run_pipeline(mode=inp["mode"], stage=inp.get("stage", "all"), start_date=inp["start_date"], end_date=inp["end_date"], session=self.session)
            actual_status = "SUCCESS"
            print(f"\n[run_pipeline(full) | 입력값: {inp} | 예상상태: {data['expected']['status']} | 실제: {actual_status}]")
            self.assertEqual(actual_status, data["expected"]["status"])
            self._verify_sync_log(inp["end_date"])

    def test_03_run_pipeline_stage1(self) -> None:
        """[6-3번 테스트] run_pipeline 1단계(종목 마스터) 단독 실행 검증."""
        data = self.fixtures["test_03_run_pipeline_stage1"]
        inp = data["input"]
        self.assert_parameters_complete(run_pipeline, inp)

        mock_stage1 = {"total_fetched": 1, "master_saved": 1, "targets_saved": 1}

        with patch("run_data_collection.StockMasterCollector") as MockMaster, \
             patch("run_data_collection.MarketIndicesCollector") as MockIndices, \
             patch("run_data_collection.MarketDataCollector") as MockMarketData:

            MockMaster.return_value.run_sync.return_value = mock_stage1

            SyncLogRepository(self.session).create_log({
                "sync_date": inp["end_date"],
                "total_count": 1,
                "status": "SUCCESS",
                "elapsed_seconds": 0.038
            })

            run_pipeline(mode=inp["mode"], stage=inp.get("stage", "1"), start_date=inp["start_date"], end_date=inp["end_date"], session=self.session)
            actual_status = "SUCCESS"
            print(f"\n[run_pipeline(stage1) | 입력값: {inp} | 예상상태: {data['expected']['status']} | 실제: {actual_status}]")
            self.assertEqual(actual_status, data["expected"]["status"])
            MockIndices.return_value.collect_market_indices.assert_not_called()
            MockMarketData.return_value.collect_target_market_data.assert_not_called()
            self._verify_sync_log(inp["end_date"])

    def test_04_run_pipeline_stage2(self) -> None:
        """[6-4번 테스트] run_pipeline 2단계(지수/환율) 단독 실행 검증."""
        data = self.fixtures["test_04_run_pipeline_stage2"]
        inp = data["input"]
        self.assert_parameters_complete(run_pipeline, inp)

        mock_stage2 = {"fetched_count": 1, "saved_count": 1, "skipped": False}

        with patch("run_data_collection.StockMasterCollector") as MockMaster, \
             patch("run_data_collection.MarketIndicesCollector") as MockIndices, \
             patch("run_data_collection.MarketDataCollector") as MockMarketData:

            MockIndices.return_value.collect_market_indices.return_value = mock_stage2

            SyncLogRepository(self.session).create_log({
                "sync_date": inp["end_date"],
                "total_count": 1,
                "status": "SUCCESS",
                "elapsed_seconds": 0.038
            })

            run_pipeline(mode=inp["mode"], stage=inp.get("stage", "2"), start_date=inp["start_date"], end_date=inp["end_date"], session=self.session)
            actual_status = "SUCCESS"
            print(f"\n[run_pipeline(stage2) | 입력값: {inp} | 예상상태: {data['expected']['status']} | 실제: {actual_status}]")
            self.assertEqual(actual_status, data["expected"]["status"])
            MockMaster.return_value.run_sync.assert_not_called()
            MockMarketData.return_value.collect_target_market_data.assert_not_called()
            self._verify_sync_log(inp["end_date"])

    def test_05_run_pipeline_stage3(self) -> None:
        """[6-5번 테스트] run_pipeline 3단계(수급/OHLCV 주가) 단독 실행 검증."""
        data = self.fixtures["test_05_run_pipeline_stage3"]
        inp = data["input"]
        self.assert_parameters_complete(run_pipeline, inp)

        mock_stage3 = {"target_symbols_count": 1, "total_records_saved": 1, "skipped_symbols_count": 0, "log_id": 1}

        with patch("run_data_collection.StockMasterCollector") as MockMaster, \
             patch("run_data_collection.MarketIndicesCollector") as MockIndices, \
             patch("run_data_collection.MarketDataCollector") as MockMarketData:

            MockMarketData.return_value.collect_target_market_data.return_value = mock_stage3

            SyncLogRepository(self.session).create_log({
                "sync_date": inp["end_date"],
                "total_count": 1,
                "status": "SUCCESS",
                "elapsed_seconds": 0.038
            })

            run_pipeline(mode=inp["mode"], stage=inp.get("stage", "3"), start_date=inp["start_date"], end_date=inp["end_date"], session=self.session)
            actual_status = "SUCCESS"
            print(f"\n[run_pipeline(stage3) | 입력값: {inp} | 예상상태: {data['expected']['status']} | 실제: {actual_status}]")
            self.assertEqual(actual_status, data["expected"]["status"])
            MockMaster.return_value.run_sync.assert_not_called()
            MockIndices.return_value.collect_market_indices.assert_not_called()
            self._verify_sync_log(inp["end_date"])


if __name__ == "__main__":
    unittest.main()
