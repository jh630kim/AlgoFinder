"""
[02번 테스트] Repository 계층 5개 클래스 전체 입출력 검증 모듈.

inspect 모듈을 활용하여 fixture 입력 파라미터 완전성을 자동 Assert 검증하고
[입력값 | 예상값 | 실제 실행 결과]를 1:1 대조 출력하는 Test02AppRepositories 클래스를 정의합니다.
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
from backend.app.repositories.target_stocks_repository import TargetStocksRepository
from backend.app.repositories.sync_log_repository import SyncLogRepository
from backend.app.repositories.market_indices_repository import MarketIndicesRepository

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "test_02_app_repositories_data.json")


class Test02AppRepositories(unittest.TestCase):
    """
    02번 테스트: 격리된 인메모리 DB 기반 5개 Repository 클래스 전수 입출력 대조 검증 클래스.
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

    def test_01_stock_master_repository(self) -> None:
        """[2-1번 테스트] StockMasterRepository 3개 메서드 전수 검증."""
        data = self.fixtures["test_01_stock_master_repository"]
        repo = StockMasterRepository(self.session)

        # 1. bulk_upsert 검증
        case_upsert = data["test_bulk_upsert"]
        self.assert_parameters_complete(repo.bulk_upsert, case_upsert["input"])
        res_upsert = repo.bulk_upsert(case_upsert["input"]["items"])
        print(f"\n[StockMaster.bulk_upsert | 입력값: {case_upsert['input']} | 예상값: {case_upsert['expected']['saved_count']} | 실제: {res_upsert}]")
        self.assertEqual(res_upsert, case_upsert["expected"]["saved_count"])

        # 2. get_by_code (존재 케이스)
        case_code = data["test_get_by_code_exists"]
        self.assert_parameters_complete(repo.get_by_code, case_code["input"])
        obj = repo.get_by_code(case_code["input"]["code"])
        actual_name = obj.name if obj else None
        print(f"[StockMaster.get_by_code | 입력값: {case_code['input']} | 예상값: {case_code['expected']['name']} | 실제: {actual_name}]")
        self.assertEqual(actual_name, case_code["expected"]["name"])

        # 3. get_by_code (미존재 케이스)
        case_none = data["test_get_by_code_not_exists"]
        self.assert_parameters_complete(repo.get_by_code, case_none["input"])
        obj_none = repo.get_by_code(case_none["input"]["code"])
        print(f"[StockMaster.get_by_code(미존재) | 입력값: {case_none['input']} | 예상값: None | 실제: {obj_none}]")
        self.assertIsNone(obj_none)

        # 4. get_all
        case_all = data["test_get_all"]
        self.assert_parameters_complete(repo.get_all, case_all["input"])
        all_list = repo.get_all()
        print(f"[StockMaster.get_all | 입력값: {case_all['input']} | 예상건수: {case_all['expected']['count']} | 실제: {len(all_list)}]")
        self.assertEqual(len(all_list), case_all["expected"]["count"])

    def test_02_market_data_repository(self) -> None:
        """[2-2번 테스트] MarketDataRepository 3개 메서드 전수 검증."""
        data = self.fixtures["test_02_market_data_repository"]
        repo = MarketDataRepository(self.session)

        # 1. bulk_upsert
        case_upsert = data["test_bulk_upsert"]
        self.assert_parameters_complete(repo.bulk_upsert, case_upsert["input"])
        res_upsert = repo.bulk_upsert(case_upsert["input"]["items"])
        print(f"\n[MarketData.bulk_upsert | 입력값: {case_upsert['input']} | 예상값: {case_upsert['expected']['saved_count']} | 실제: {res_upsert}]")
        self.assertEqual(res_upsert, case_upsert["expected"]["saved_count"])

        # 2. get_by_symbol_and_date (존재 케이스)
        case_get = data["test_get_by_symbol_and_date_exists"]
        self.assert_parameters_complete(repo.get_by_symbol_and_date, case_get["input"])
        obj = repo.get_by_symbol_and_date(case_get["input"]["symbol"], case_get["input"]["date_str"])
        actual_close = obj.close_price if obj else None
        print(f"[MarketData.get_by_symbol_and_date | 입력값: {case_get['input']} | 예상종가: {case_get['expected']['close_price']} | 실제종가: {actual_close}]")
        self.assertEqual(actual_close, case_get["expected"]["close_price"])

        # 3. get_by_symbol_and_date (미존재 케이스)
        case_none = data["test_get_by_symbol_and_date_not_exists"]
        self.assert_parameters_complete(repo.get_by_symbol_and_date, case_none["input"])
        obj_none = repo.get_by_symbol_and_date(case_none["input"]["symbol"], case_none["input"]["date_str"])
        print(f"[MarketData.get_by_symbol_and_date(미존재) | 입력값: {case_none['input']} | 예상값: None | 실제: {obj_none}]")
        self.assertIsNone(obj_none)

        # 4. get_max_date
        case_max = data["test_get_max_date"]
        self.assert_parameters_complete(repo.get_max_date, case_max["input"])
        max_d = repo.get_max_date(case_max["input"]["symbol"])
        print(f"[MarketData.get_max_date | 입력값: {case_max['input']} | 예상최근일자: {case_max['expected']['max_date']} | 실제: {max_d}]")
        self.assertEqual(max_d, case_max["expected"]["max_date"])

    def test_03_target_stocks_repository(self) -> None:
        """[2-3번 테스트] TargetStocksRepository 2개 메서드 전수 검증."""
        data = self.fixtures["test_03_target_stocks_repository"]
        repo = TargetStocksRepository(self.session)

        # 1. sync_targets
        case_sync = data["test_sync_targets"]
        self.assert_parameters_complete(repo.sync_targets, case_sync["input"])
        res_sync = repo.sync_targets(case_sync["input"]["symbols"])
        print(f"\n[TargetStocks.sync_targets | 입력값: {case_sync['input']} | 예상건수: {case_sync['expected']['count']} | 실제: {res_sync}]")
        self.assertEqual(res_sync, case_sync["expected"]["count"])

        # 2. get_all_symbols
        case_get = data["test_get_all_symbols"]
        self.assert_parameters_complete(repo.get_all_symbols, case_get["input"])
        symbols = repo.get_all_symbols()
        print(f"[TargetStocks.get_all_symbols | 입력값: {case_get['input']} | 예상목록: {case_get['expected']['symbols']} | 실제: {sorted(symbols)}]")
        self.assertEqual(sorted(symbols), sorted(case_get["expected"]["symbols"]))

    def test_04_sync_log_repository(self) -> None:
        """[2-4번 테스트] SyncLogRepository 2개 메서드 전수 검증."""
        data = self.fixtures["test_04_sync_log_repository"]
        repo = SyncLogRepository(self.session)

        # 1. create_log
        case_create = data["test_create_log"]
        self.assert_parameters_complete(repo.create_log, case_create["input"])
        log_obj = repo.create_log(case_create["input"]["log_data"])
        actual_status = log_obj.status if log_obj else None
        print(f"\n[SyncLog.create_log | 입력값: {case_create['input']} | 예상상태: {case_create['expected']['status']} | 실제: {actual_status}]")
        self.assertEqual(actual_status, case_create["expected"]["status"])

        # 2. get_latest_log
        case_latest = data["test_get_latest_log"]
        self.assert_parameters_complete(repo.get_latest_log, case_latest["input"])
        latest_obj = repo.get_latest_log()
        actual_date = latest_obj.sync_date if latest_obj else None
        print(f"[SyncLog.get_latest_log | 입력값: {case_latest['input']} | 예상일자: {case_latest['expected']['sync_date']} | 실제: {actual_date}]")
        self.assertEqual(actual_date, case_latest["expected"]["sync_date"])

    def test_05_market_indices_repository(self) -> None:
        """[2-5번 테스트] MarketIndicesRepository 3개 메서드 전수 검증."""
        data = self.fixtures["test_05_market_indices_repository"]
        repo = MarketIndicesRepository(self.session)

        # 1. bulk_upsert
        case_upsert = data["test_bulk_upsert"]
        self.assert_parameters_complete(repo.bulk_upsert, case_upsert["input"])
        res_upsert = repo.bulk_upsert(case_upsert["input"]["items"])
        print(f"\n[MarketIndices.bulk_upsert | 입력값: {case_upsert['input']} | 예상값: {case_upsert['expected']['saved_count']} | 실제: {res_upsert}]")
        self.assertEqual(res_upsert, case_upsert["expected"]["saved_count"])

        # 2. get_by_date (존재 케이스)
        case_get = data["test_get_by_date_exists"]
        self.assert_parameters_complete(repo.get_by_date, case_get["input"])
        obj = repo.get_by_date(case_get["input"]["date_str"])
        actual_kospi = obj.kospi_close if obj else None
        print(f"[MarketIndices.get_by_date | 입력값: {case_get['input']} | 예상코스피: {case_get['expected']['kospi_close']} | 실제: {actual_kospi}]")
        self.assertEqual(actual_kospi, case_get["expected"]["kospi_close"])

        # 3. get_by_date (미존재 케이스)
        case_none = data["test_get_by_date_not_exists"]
        self.assert_parameters_complete(repo.get_by_date, case_none["input"])
        obj_none = repo.get_by_date(case_none["input"]["date_str"])
        print(f"[MarketIndices.get_by_date(미존재) | 입력값: {case_none['input']} | 예상값: None | 실제: {obj_none}]")
        self.assertIsNone(obj_none)

        # 4. get_max_date
        case_max = data["test_get_max_date"]
        self.assert_parameters_complete(repo.get_max_date, case_max["input"])
        max_d = repo.get_max_date()
        print(f"[MarketIndices.get_max_date | 입력값: {case_max['input']} | 예상최근일자: {case_max['expected']['max_date']} | 실제: {max_d}]")
        self.assertEqual(max_d, case_max["expected"]["max_date"])


if __name__ == "__main__":
    unittest.main()
