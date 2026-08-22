"""
[05번 테스트 -> 07번 테스트 이동 리다이렉트 모듈]

전략 엔진 테스트 순번이 05번에서 07번(test_07_strategy_engine.py)으로 변경되었습니다.
"""

from backend.tests.test_07_strategy_engine import Test07StrategyEngine

# 07번 테스트 클래스 상속 및 재사용
Test05StrategyEngine = Test07StrategyEngine
