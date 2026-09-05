"""FinanceDataReader 호출에 강제 타임아웃을 씌우는 헬퍼 모듈 (fdr_safe.py).

`fdr.DataReader` 는 timeout 인자를 지원하지 않아, 데이터 소스가 연결만 받고 응답을
주지 않으면(특히 GitHub Actions 공유 IP의 rate-limit 시) 호출이 예외 없이 무한 대기한다.
별도 스레드 풀에서 실행하고 제한 시간 내 결과가 없으면 TimeoutError 를 던져,
호출부의 재시도/백오프 로직이 정상 작동하도록 한다.

멈춘 스레드는 강제 종료할 수 없어 풀에 남지만(최대 max_workers 개), 수집은 짧게 끝나는
배치성 작업이라 프로세스 종료로 정리되며, 웹 서빙 경로에서는 애초에 호출되지 않는다.
"""

import concurrent.futures as _cf

# FinanceDataReader 는 웹 서빙(requirements-web) 대상이 아니므로 지연 import 한다.
_POOL = _cf.ThreadPoolExecutor(max_workers=8, thread_name_prefix="fdr")
DEFAULT_TIMEOUT = 12.0  # 초. 정상 호출은 수 초 내 완료된다.


def read_fdr(symbol: str, start_date: str, end_date: str,
             timeout: float = DEFAULT_TIMEOUT):
    """`fdr.DataReader(symbol, start_date, end_date)` 를 `timeout` 초 내로 강제 실행합니다.

    :param symbol: FDR 심볼 (종목코드 또는 'KS11'/'US500'/'USD/KRW' 등)
    :param start_date: 시작일자 (YYYYMMDD)
    :param end_date: 종료일자 (YYYYMMDD)
    :param timeout: 제한 시간(초). 기본 12.
    :return: pandas.DataFrame (FDR 반환값 그대로)
    :raises TimeoutError: 제한 시간 내 응답이 없을 때. 호출부에서 재시도로 흡수한다.
    """
    import FinanceDataReader as fdr

    future = _POOL.submit(fdr.DataReader, symbol, start_date, end_date)
    return future.result(timeout=timeout)
