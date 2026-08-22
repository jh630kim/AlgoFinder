"""
[08번 테스트] StrategyLeaderboardRepository & StrategyTradeLogsRepository 통합 데이터베이스 검증 모듈.

inspect 모듈을 활용하여 입력 파라미터 완전성을 자동 Assert 검증하고
전략 리더보드 및 체결 로그의 Upsert, Bulk Insert, 조회 기능을 1:1 대조 검증합니다.
"""

import os
import json
import inspect
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.core.database import Base
from backend.app.repositories.strategy_leaderboard_repository import StrategyLeaderboardRepository
from backend.app.repositories.strategy_trade_logs_repository import StrategyTradeLogsRepository

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "test_08_strategy_leaderboard_repository_data.json")


class Test08StrategyLeaderboardRepository(unittest.TestCase):
    """
    08번 테스트: StrategyLeaderboardRepository & StrategyTradeLogsRepository 통합 검증 클래스.
    """

    def setUp(self) -> None:
        """인메모리 SQLite 세션 초기화 및 Fixture 로드."""
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

        with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
            self.fixtures = json.load(f)

        self.leaderboard_repo = StrategyLeaderboardRepository(self.session)
        self.trade_logs_repo = StrategyTradeLogsRepository(self.session)

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

    def test_01_upsert_leaderboard(self) -> None:
        """[8-1번 테스트] StrategyLeaderboardRepository.upsert_leaderboard_entry 검증."""
        data = self.fixtures["test_01_upsert_leaderboard"]
        inp = data["input"]
        exp = data["expected"]

        self.assert_parameters_complete(self.leaderboard_repo.upsert_leaderboard_entry, {"entry_dict": inp})

        res = self.leaderboard_repo.upsert_leaderboard_entry(inp)
        print(f"\n[Leaderboard.upsert | 입력값: {inp['combo_name']} | 예상수익률: {exp['total_return_pct']}% | 실제: {res.total_return_pct}%]")
        self.assertEqual(res.combo_id, exp["combo_id"])
        self.assertEqual(res.combo_name, exp["combo_name"])
        self.assertEqual(res.total_return_pct, exp["total_return_pct"])

    def test_02_bulk_insert_trade_logs(self) -> None:
        """[8-2번 테스트] StrategyTradeLogsRepository.bulk_insert_trade_logs 및 조회 검증."""
        data = self.fixtures["test_02_bulk_insert_trade_logs"]
        inp = data["input"]
        exp = data["expected"]

        self.assert_parameters_complete(self.trade_logs_repo.bulk_insert_trade_logs, {"logs_list": inp})

        saved_count = self.trade_logs_repo.bulk_insert_trade_logs(inp)
        logs = self.trade_logs_repo.get_logs_by_combo(inp[0]["combo_id"])
        print(f"\n[TradeLogs.bulk_insert | 입력건수: {len(inp)} | 예상건수: {exp['saved_count']} | 실제건수: {saved_count}]")
        self.assertEqual(saved_count, exp["saved_count"])
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].symbol, "005930")


if __name__ == "__main__":
    unittest.main()
