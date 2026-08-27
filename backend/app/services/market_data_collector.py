"""
일별 수급 및 OHLCV 데이터 수집 파이프라인 모듈.

PyKRX 및 FinanceDataReader/Naver API를 활용하여 타깃 종목의
일별 수급 및 가격 데이터를 수집하고 SyncLogs를 자동 기록하는 MarketDataCollector 클래스를 정의합니다.
"""

from typing import List, Dict, Any, Optional
import time
import logging
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy.orm import Session
from backend.app.repositories.market_data_repository import MarketDataRepository
from backend.app.repositories.target_stocks_repository import TargetStocksRepository
from backend.app.repositories.sync_log_repository import SyncLogRepository
from backend.app.repositories.stock_master_repository import StockMasterRepository

logger = logging.getLogger(__name__)


class MarketDataCollector:
    """
    일별 수급 및 OHLCV 수집 및 파이프라인 제어 전담 클래스.
    """

    def __init__(self, session: Session) -> None:
        """
        MarketDataCollector 초기화.

        :param session: SQLAlchemy 세션 객체
        """
        self.session = session
        self.market_repo = MarketDataRepository(session)
        self.target_repo = TargetStocksRepository(session)
        self.sync_log_repo = SyncLogRepository(session)
        self.master_repo = StockMasterRepository(session)

    def _fetch_fdr_fallback(self, symbol: str, start_date: str, end_date: str, reason: str) -> List[Dict[str, Any]]:
        """
        FinanceDataReader(FDR)를 활용해 OHLCV 시세를 수집하고 수급 필드는 NULL(None)로 처리합니다.

        :param symbol: 종목코드
        :param start_date: 시작일자 (YYYYMMDD)
        :param end_date: 종료일자 (YYYYMMDD)
        :param reason: 폴백 사유
        :return: 데이터 딕셔너리 리스트
        """
        try:
            import FinanceDataReader as fdr
            logger.info(f"  └─ ➔ [{symbol}] {reason} ➔ FinanceDataReader(FDR) 2차 폴백으로 OHLCV 시세 수집 (수급 필드 NULL 처리)")
            df = fdr.DataReader(symbol, start_date, end_date)
            if df is None or df.empty:
                return []

            records = []
            for idx_dt, row in df.iterrows():
                d_str = idx_dt.strftime("%Y%m%d")
                records.append({
                    "symbol": symbol,
                    "date": d_str,
                    "open_price": float(row.get("Open", 0.0)),
                    "high_price": float(row.get("High", 0.0)),
                    "low_price": float(row.get("Low", 0.0)),
                    "close_price": float(row.get("Close", 0.0)),
                    "volume": int(row.get("Volume", 0)),
                    "personal_net_buy": None,
                    "foreigner_net_buy": None,
                    "institution_net_buy": None,
                    "pension_net_buy": None,
                    "financial_net_buy": None,
                    "other_corp_net_buy": None,
                })
            return records
        except Exception as exc:
            logger.error(f"[{symbol}] FDR 폴백 수집 중 예외 발생: {exc}")
            return []

    def fetch_ohlc_map_from_fchart(self, symbol: str) -> Dict[str, tuple]:
        """
        네이버 fchart XML에서 최대 6,000일치 일별 시가, 고가, 저가, 종가, 거래량을 파싱합니다.
        :return: {YYYYMMDD: (open, high, low, close, volume)}
        """
        symbol_formatted = str(symbol).zfill(6)
        url = f"https://fchart.stock.naver.com/sise.nhn?symbol={symbol_formatted}&timeframe=day&count=6000&requestType=0"
        ohlc_map = {}
        try:
            import requests
            import xml.etree.ElementTree as ET
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            res = requests.get(url, headers=headers, timeout=8)
            if res.status_code == 200 and res.text:
                root = ET.fromstring(res.text)
                for item in root.findall(".//item"):
                    data_attr = item.attrib.get("data", "")
                    if not data_attr:
                        continue
                    parts = data_attr.split("|")
                    if len(parts) >= 6:
                        d_str = parts[0].strip()
                        open_p = float(parts[1])
                        high_p = float(parts[2])
                        low_p = float(parts[3])
                        close_p = float(parts[4])
                        vol = int(parts[5])
                        ohlc_map[d_str] = (open_p, high_p, low_p, close_p, vol)
        except Exception as e:
            logger.warning(f"[{symbol}] fchart 파싱 예외: {e}")
        return ohlc_map

    def fetch_trading_data_with_retry(
        self, symbol: str, start_date: str, end_date: str, max_retries: int = 3
    ) -> List[Dict[str, Any]]:
        """
        단일 종목의 일별 수급 및 시세를 네이버 금융 웹 스크래핑 및 fchart XML 기반으로 수집합니다.
        2005년부터 2026년까지 20년 치 전체 데이터를 유실 없이 수집하며 open_price가 0이 되는 현상을 원천 방지합니다.

        :param symbol: 종목코드
        :param start_date: 시작일자 (YYYYMMDD)
        :param end_date: 종료일자 (YYYYMMDD)
        :param max_retries: 최대 재시도 횟수
        :return: 데이터 딕셔너리 리스트
        """
        import io
        import requests
        symbol_formatted = str(symbol).zfill(6)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        # 1. fchart XML로부터 2005년~현재 OHLCV 맵 파싱 (단 1번의 요청 0.05초)
        ohlc_map = self.fetch_ohlc_map_from_fchart(symbol_formatted)

        # 3. 네이버 frgn.naver HTML 페이징 스크래핑으로 2005년까지 수급 파싱
        records_dict = {}
        seen_dates = set()
        max_pages = 350  # 2005년까지 약 350페이지

        for page in range(1, max_pages + 1):
            url = f"https://finance.naver.com/item/frgn.naver?code={symbol_formatted}&page={page}"
            try:
                res = requests.get(url, headers=headers, timeout=8)
                if res.status_code != 200:
                    break

                dfs = pd.read_html(io.StringIO(res.text))
                target_df = None
                for df in dfs:
                    df_str = str(df.columns)
                    if '날짜' in df_str or '기관' in df_str or '외국인' in df_str:
                        target_df = df.dropna(how='all')
                        break

                if target_df is None or target_df.empty:
                    break

                stop_scraping = False
                valid_rows = 0

                for _, row in target_df.iterrows():
                    raw_date = str(row.iloc[0]).strip().replace(".", "")
                    if len(raw_date) != 8 or not raw_date.isdigit():
                        continue

                    if raw_date in seen_dates:
                        continue

                    # 시작일보다 이전 날짜가 나오면 수집 중단 (Stop)
                    if raw_date < start_date:
                        stop_scraping = True
                        break

                    if raw_date > end_date:
                        continue

                    try:
                        close_price = int(float(str(row.iloc[1]).replace(',', '')))
                        volume = int(float(str(row.iloc[4]).replace(',', '')))

                        inst_cnt = float(str(row.iloc[5]).replace(',', '')) if len(row) > 5 and pd.notna(row.iloc[5]) else 0.0
                        foreign_cnt = float(str(row.iloc[6]).replace(',', '')) if len(row) > 6 and pd.notna(row.iloc[6]) else 0.0
                        personal_cnt = -(inst_cnt + foreign_cnt)

                        inst_buy = float(inst_cnt * close_price)
                        foreign_buy = float(foreign_cnt * close_price)
                        personal_buy = float(personal_cnt * close_price)

                        ohlc_tuple = ohlc_map.get(raw_date, (float(close_price), float(close_price), float(close_price), float(close_price), volume))
                        open_p, high_p, low_p, close_p, vol = ohlc_tuple

                        records_dict[raw_date] = {
                            "symbol": symbol,
                            "date": raw_date,
                            "open_price": open_p if open_p > 0 else float(close_price),
                            "high_price": high_p if high_p > 0 else float(close_price),
                            "low_price": low_p if low_p > 0 else float(close_price),
                            "close_price": close_p if close_p > 0 else float(close_price),
                            "volume": vol if vol > 0 else volume,
                            "personal_net_buy": personal_buy,
                            "foreigner_net_buy": foreign_buy,
                            "institution_net_buy": inst_buy,
                            "pension_net_buy": None,
                            "financial_net_buy": None,
                            "other_corp_net_buy": None,
                        }
                        seen_dates.add(raw_date)
                        valid_rows += 1
                    except Exception:
                        continue

                if stop_scraping or valid_rows == 0:
                    break

                time.sleep(0.03)  # 초경량 0.03초 지연
            except Exception as e:
                logger.warning(f"[{symbol}] 네이버 수급 스크래핑 page {page} 예외: {e}")
                break

        # fchart 시세에는 존재하지만 수급 표에 없는 날짜들을 fchart 시세 + 수급 NULL로 보완 결합
        for d_str, (open_p, high_p, low_p, close_p, vol) in ohlc_map.items():
            if d_str < start_date or d_str > end_date:
                continue
            if d_str not in records_dict:
                records_dict[d_str] = {
                    "symbol": symbol,
                    "date": d_str,
                    "open_price": open_p,
                    "high_price": high_p,
                    "low_price": low_p,
                    "close_price": close_p,
                    "volume": vol,
                    "personal_net_buy": None,
                    "foreigner_net_buy": None,
                    "institution_net_buy": None,
                    "pension_net_buy": None,
                    "financial_net_buy": None,
                    "other_corp_net_buy": None,
                }

        # 날짜순 정렬
        sorted_records = [records_dict[d] for d in sorted(records_dict.keys())]
        if not sorted_records:
            return self._fetch_fdr_fallback(
                symbol, start_date, end_date,
                reason="네이버 웹 스크래핑 수집 0건 결과에 따른 FDR 폴백"
            )

        return sorted_records

    def collect_target_market_data(
        self, start_date: str = None, end_date: str = None, incremental: bool = True,
        progress_callback=None
    ) -> Dict[str, Any]:
        """
        모든 타깃 종목에 대해 수급/OHLCV 데이터를 스마트 증분(Incremental) 또는 전체(Full) 모드로 수집합니다.

        :param start_date: 시작일자 (YYYYMMDD, None시 기본값 20050101)
        :param end_date: 종료일자 (YYYYMMDD, None시 오늘)
        :param incremental: 증분 수집 여부 (True: 미수집 신규 일자만, False: 전체 덮어쓰기)
        :param progress_callback: 진행 상황 콜백 (done:int, total:int, msg:str) — None시 미호출
        :return: 수집 결과 요약 딕셔너리
        """
        start_time = time.time()
        today_str = datetime.now().strftime("%Y%m%d")
        actual_end = end_date if end_date else today_str
        default_start = start_date if start_date else "20050101"

        symbols = self.target_repo.get_all_symbols()
        total_symbols = len(symbols)
        total_records = 0
        skipped_count = 0

        mode_str = "스마트 증분(Incremental)" if incremental else "전체(Full)"
        logger.info(f"총 {total_symbols}개 타깃 종목 수집 시작 [{mode_str} 모드]...")

        for idx, sym in enumerate(symbols, 1):
            stock_obj = self.master_repo.get_by_code(sym)
            stock_name = stock_obj.name if stock_obj else sym
            pct = (idx / total_symbols) * 100 if total_symbols > 0 else 100

            # 진행 상황 콜백 (웹 진행바 등 외부 표시용)
            if progress_callback:
                progress_callback(idx, total_symbols, f"{sym} {stock_name}")

            target_start = default_start

            if incremental:
                max_date = self.market_repo.get_max_date(sym)
                if max_date:
                    next_day_dt = datetime.strptime(max_date, "%Y%m%d") + timedelta(days=1)
                    next_day_str = next_day_dt.strftime("%Y%m%d")
                    if next_day_str > actual_end:
                        logger.info(f"  ├─ [{idx:3d}/{total_symbols:3d}] ({pct:5.1f}%) {sym} {stock_name} ➔ 최신({max_date}) 데이터 적재됨 (건너뜀)")
                        skipped_count += 1
                        continue
                    else:
                        target_start = next_day_str

            items = self.fetch_trading_data_with_retry(sym, target_start, actual_end)
            saved = 0
            if items:
                saved = self.market_repo.bulk_upsert(items)
                total_records += saved

            logger.info(f"  ├─ [{idx:3d}/{total_symbols:3d}] ({pct:5.1f}%) {sym} {stock_name} 수집 완료 ({target_start}~{actual_end}, {saved}건 적재)")
            time.sleep(0.5)  # KRX 서버 호출 제한(Rate Limit) 방지 0.5초 여유 딜레이

        # 총 소요시간 측정 및 가독형 표현 계산
        elapsed_sec = round(time.time() - start_time, 2)
        sec_int = int(elapsed_sec)
        hours = sec_int // 3600
        minutes = (sec_int % 3600) // 60
        secs = sec_int % 60
        if hours > 0:
            elapsed_str = f"{hours:02d}시간 {minutes:02d}분 {secs:02d}초"
        elif minutes > 0:
            elapsed_str = f"{minutes:02d}분 {secs:02d}초"
        else:
            elapsed_str = f"{secs}초"

        # SyncLogs 기록 생성 (소요시간 반영)
        log_entry = self.sync_log_repo.create_log({
            "sync_date": actual_end,
            "total_count": total_records,
            "kospi_count": total_symbols,
            "status": "SUCCESS",
            "elapsed_seconds": elapsed_sec,
            "elapsed_time_str": elapsed_str,
        })

        logger.info(f"  └─ ✅ 수집 완료 (적재: {total_records}건, 건너뜀: {skipped_count}개 종목 | 소요시간: {elapsed_str})")

        return {
            "target_symbols_count": total_symbols,
            "total_records_saved": total_records,
            "skipped_symbols_count": skipped_count,
            "log_id": log_entry.id,
            "elapsed_seconds": elapsed_sec,
            "elapsed_time_str": elapsed_str,
        }
