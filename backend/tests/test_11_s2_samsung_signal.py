"""
AlgoFinder backend/tests/test_11_s2_samsung_signal.py
20260226부터 최신 거래일까지 삼성전자(005930) DB 데이터를 S2BreakoutStrategy 백엔드 전략 엔진에 대입하고,
매수(BUY) 및 매도(SELL) 시그널 출력 결과를 1:1로 정밀 대조하고 발생 날짜 목록을 추출하는 단위 테스트 모듈.
"""

import inspect
import pytest
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import settings
from backend.app.models.investor_trading_daily import InvestorTradingDaily
from backend.app.services.strategies.s2_breakout import S2BreakoutStrategy


class Test11S2SamsungSignal:
    """삼성전자 S2 RSI 돌파 전략 시그널 1:1 정밀 대조 및 날짜 추출 테스트 클래스."""

    @pytest.fixture(autouse=True)
    def setup_db_session(self):
        """데이터베이스 세션 생성 및 정리 픽스처."""
        engine = create_engine(settings.DATABASE_URL)
        Session = sessionmaker(bind=engine)
        self.session = Session()
        yield
        self.session.close()

    def test_11_s2_samsung_signal_calculation(self):
        """
        20260226부터 최신 거래일까지 삼성전자(005930) 주가/수급 데이터를 불러와
        S2BreakoutStrategy 전략 엔진의 시그널 산출 결과 및 시그널 발생 날짜를 1:1로 비교 검증한다.
        """
        # 1. inspect를 활용한 매개변수 완전성 검증 (Assert)
        strategy = S2BreakoutStrategy()
        calc_sig = inspect.signature(strategy.calculate_indicators)
        params = list(calc_sig.parameters.keys())
        print(f"\n[Inspect 매개변수 검증] S2BreakoutStrategy.calculate_indicators params: {params}")
        assert "df" in params, "calculate_indicators 메서드는 'df' 매개변수를 필수 포함해야 합니다."

        # 2. 삼성전자(005930) 20260226 ~ 최신 거래일 DB 데이터 쿼리
        symbol = "005930"  # 삼성전자 종목코드
        start_date = "20260226"

        records = (
            self.session.query(InvestorTradingDaily)
            .filter(
                InvestorTradingDaily.symbol == symbol,
                InvestorTradingDaily.date >= start_date
            )
            .order_by(InvestorTradingDaily.date.asc())
            .all()
        )

        assert len(records) > 0, f"DB에 삼성전자({symbol}) {start_date} 이후 데이터가 존재하지 않습니다."

        # 3. Pandas DataFrame 변환 (전략 엔진 요구 규격)
        data_list = []
        for r in records:
            data_list.append({
                "date": r.date,
                "symbol": r.symbol,
                "close": float(r.close_price or 0),
                "open": float(r.open_price or 0),
                "high": float(r.high_price or 0),
                "low": float(r.low_price or 0),
                "close_price": float(r.close_price or 0),
                "open_price": float(r.open_price or 0),
                "high_price": float(r.high_price or 0),
                "low_price": float(r.low_price or 0),
                "volume": float(r.volume or 0),
                "foreigner_net_buy": float(r.foreigner_net_buy or 0),
                "institution_net_buy": float(r.institution_net_buy or 0),
                "personal_net_buy": float(r.personal_net_buy or 0),
                "pension_net_buy": float(r.pension_net_buy or 0),
            })

        df_input = pd.DataFrame(data_list)

        # 4. 백엔드 S2BreakoutStrategy 전략 엔진 계산 실행
        df_result = strategy.calculate_indicators(df_input)

        # 5. 시그널 결과 추출 및 1:1 대조 터미널 출력
        buy_signals = df_result[df_result['signal_buy'] == True]
        sell_signals = df_result[df_result['signal_sell'] == True]

        buy_dates = buy_signals['date'].tolist()
        sell_dates = sell_signals['date'].tolist()

        print("\n=========================================================================================")
        print(f"[삼성전자(005930) {start_date} ~ 최신 거래일 S2 전략 시그널 1:1 정밀 검증 표]")
        print("=========================================================================================")
        print(f"{'날짜 (date)':<12} | {'종가 (close)':<10} | {'RSI(14)':<10} | {'RSI Signal(9)':<12} | {'S2 시그널'}")
        print("-----------------------------------------------------------------------------------------")

        for idx, row in df_result.iterrows():
            d = row['date']
            close_val = f"{int(row['close_price']):,}" if pd.notnull(row['close_price']) else "-"
            rsi_val = f"{row['rsi']:.2f}%" if pd.notnull(row.get('rsi')) else "-"
            sig_val = f"{row['signal']:.2f}%" if pd.notnull(row.get('signal')) else "-"

            sig_str = "관망"
            if row.get('signal_buy') == True:
                sig_str = "[BUY] 매수 (^)"
            elif row.get('signal_sell') == True:
                sig_str = "[SELL] 매도 (v)"

            print(f"{d:<12} | {close_val:<10} | {rsi_val:<10} | {sig_val:<12} | {sig_str}")

        print("=========================================================================================")
        print(f"[1:1 정답/실제 비교 Summary]")
        print(f"  - 조회 총 거래일수: {len(df_result)}일")
        print(f"  - [BUY] S2 매수 시그널 발생 건수: {len(buy_dates)}건 (발생 날짜: {buy_dates if buy_dates else '없음'})")
        print(f"  - [SELL] S2 매도 시그널 발생 건수: {len(sell_dates)}건 (발생 날짜: {sell_dates if sell_dates else '없음'})")
        print("=========================================================================================\n")

        # 6. Assert 대조 검증
        assert "signal_buy" in df_result.columns, "결과 DataFrame에 signal_buy 컬럼이 존재해야 합니다."
        assert "signal_sell" in df_result.columns, "결과 DataFrame에 signal_sell 컬럼이 존재해야 합니다."
        assert "rsi" in df_result.columns, "결과 DataFrame에 rsi 컬럼이 존재해야 합니다."
        assert "signal" in df_result.columns, "결과 DataFrame에 signal 컬럼이 존재해야 합니다."
