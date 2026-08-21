"""
[01번 테스트] ORM 모델과 실제 DB 스키마 1:1 대조 및 입출력 검증 모듈.

SQLAlchemy ORM 모델에 정의된 정답(Expected) 스키마와
실제 SQLite DB(data/app.db)의 실제 출력(Actual) 구조를 1:1로 대조 검증하는 AppCoreModelsTest 클래스를 정의합니다.
"""

import sqlite3
import inspect
import unittest
from typing import Dict, Any
from backend.app.core.database import db_manager, Base
import backend.app.models  # noqa: F401 모델 등록용 임포트


class Test01AppCoreModels(unittest.TestCase):
    """
    01번 테스트: ORM 모델(정답)과 실제 DB 구조(실제 출력) 1:1 대조 단위 테스트 클래스.
    """

    def setUp(self) -> None:
        """DB 세션 및 스키마 사전 점검."""
        self.db_path = "data/app.db"
        db_manager.create_all_tables()

    def assert_parameters_complete(self, func, input_dict: dict) -> None:
        """
        inspect 모듈을 사용하여 메서드 요구 파라미터 완전성을 자동 검증(Assert)합니다.

        :param func: 검증 대상 메서드
        :param input_dict: 입력값 딕셔너리
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

    def get_actual_db_schema(self) -> Dict[str, Dict[str, Any]]:
        """
        실제 SQLite DB(data/app.db)로부터 테이블 및 컬럼 구조(Actual)를 읽어옵니다.

        :return: {테이블명: {컬럼명: 컬럼정보}} 딕셔너리
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall() if not row[0].startswith("sqlite_")]

        actual_schema: Dict[str, Dict[str, Any]] = {}
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table})")
            cols = {}
            for col in cursor.fetchall():
                cols[col[1]] = {
                    "type": col[2].upper(),
                    "notnull": bool(col[3]),
                    "pk": bool(col[5]),
                }
            actual_schema[table] = cols

        conn.close()
        return actual_schema

    def get_expected_orm_schema(self) -> Dict[str, Dict[str, Any]]:
        """
        SQLAlchemy ORM 모델(Base.metadata)로부터 정답 스키마(Expected)를 추출합니다.

        :return: {테이블명: {컬럼명: 컬럼정보}} 딕셔너리
        """
        expected_schema: Dict[str, Dict[str, Any]] = {}
        for table_name, table_obj in Base.metadata.tables.items():
            cols = {}
            for column in table_obj.columns:
                cols[column.name] = {
                    "type": str(column.type).upper(),
                    "notnull": not column.nullable,
                    "pk": column.primary_key,
                }
            expected_schema[table_name] = cols
        return expected_schema

    def test_01_compare_orm_expected_vs_db_actual(self) -> None:
        """
        [1번 테스트] ORM 정답(Expected)과 실제 DB 출력(Actual) 1:1 대조 검증.
        """
        expected = self.get_expected_orm_schema()
        actual = self.get_actual_db_schema()

        print("\n==========================================")
        print("[01번 테스트] ORM 모델(정답) vs 실제 DB(출력) 1:1 스키마 대조")
        print("==========================================")

        self.assertEqual(
            set(expected.keys()), set(actual.keys()),
            f"테이블 불일치! 정답: {set(expected.keys())} vs 실제: {set(actual.keys())}"
        )

        for table_name, exp_cols in expected.items():
            act_cols = actual.get(table_name, {})
            print(f"\n[테이블: {table_name}]")

            self.assertEqual(
                set(exp_cols.keys()), set(act_cols.keys()),
                f"[{table_name}] 컬럼 구성 불일치! 정답: {set(exp_cols.keys())} vs 실제: {set(act_cols.keys())}"
            )

            for col_name, exp_info in exp_cols.items():
                act_info = act_cols.get(col_name, {})
                print(f"  - 컬럼: {col_name:<20} | 정답(Expected): {exp_info} | 실제(Actual): {act_info}")
                self.assertEqual(
                    exp_info["pk"], act_info.get("pk"),
                    f"[{table_name}.{col_name}] PK 불일치! 정답: {exp_info['pk']} vs 실제: {act_info.get('pk')}"
                )


if __name__ == "__main__":
    unittest.main()
