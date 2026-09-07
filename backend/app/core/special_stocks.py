"""
특별관리종목 설정 로더 모듈.

지수(KOSPI 200 / KOSDAQ 150) 자동 편입과 무관하게 데이터 수집 타깃 및
백테스트·투자제안·모의투자 유니버스에 항상 포함시킬 "특별관리종목" 코드 목록을
`data/special_stocks.json` 단일 소스에서 읽어오는 SpecialStocks 클래스를 정의합니다.
"""

import json
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

# all_stock_master.sector 에 부여하는 특별관리종목 전용 라벨
SPECIAL_SECTOR_LABEL = "특별관리"

# 백테스트·투자제안·모의투자가 공유하는 기본 대상 지수군.
# 특별관리 라벨을 포함시켜, 설정 파일에 등재된 종목이 전 기능에 자동 편입되게 한다.
DEFAULT_TARGET_SECTORS = ["KOSPI 200", "KOSDAQ 150", SPECIAL_SECTOR_LABEL]

# 프로젝트 루트 기준 설정 파일 경로 (backend/app/core/ 에서 3단계 상위가 저장소 루트)
_CONFIG_PATH = Path(__file__).resolve().parents[3] / "data" / "special_stocks.json"


class SpecialStocks:
    """특별관리종목 설정 파일(`data/special_stocks.json`) 접근 전담 클래스."""

    @classmethod
    def codes(cls) -> List[str]:
        """
        특별관리종목 6자리 코드 리스트를 반환합니다.

        :return: 종목코드 문자열 리스트(중복 제거, 입력 순서 유지).
                 파일이 없거나 형식 오류 시 빈 리스트.
        """
        codes: List[str] = []
        for item in cls._read_raw():
            # 문자열 직접 기재("950160")와 {"code": "950160"} 객체 형태를 모두 허용
            raw = item if isinstance(item, str) else (item or {}).get("code", "")
            code = str(raw).strip().zfill(6)
            if code.isdigit() and len(code) == 6 and code not in codes:
                codes.append(code)
        return codes

    @classmethod
    def _read_raw(cls) -> list:
        """설정 파일에서 stocks 배열(원본 항목 리스트)을 읽습니다. 실패 시 빈 리스트."""
        if not _CONFIG_PATH.exists():
            logger.info("특별관리종목 설정 파일 없음: %s (빈 목록으로 진행)", _CONFIG_PATH)
            return []
        try:
            data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("특별관리종목 설정 파일 파싱 실패(%s): %s", _CONFIG_PATH, exc)
            return []
        stocks = data.get("stocks", []) if isinstance(data, dict) else data
        return stocks if isinstance(stocks, list) else []
