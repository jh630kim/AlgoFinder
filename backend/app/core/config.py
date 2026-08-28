"""
시스템 환경 설정 관리 모듈.

이 모듈은 `.env` 파일 및 환경 변수로부터 DB 접속 정보, API 키 등
시스템 전역 설정을 로드하고 관리하는 역할을 전담합니다.
"""

import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# .env 환경 변수를 os.environ에 자동 바인딩
load_dotenv()


class Settings(BaseSettings):
    """
    시스템 전역 환경 변수 설정 클래스.

    pydantic-settings를 사용하여 환경 변수를 검증하고 로드합니다.
    """
    APP_NAME: str = "AlgoFinder"
    ENV: str = "development"

    # 실행 프로필 및 배포 모드
    # APP_PROFILE: "full"(로컬, 전체 화면) | "web"(Koyeb, 투자제안 모바일만)
    APP_PROFILE: str = "full"
    # READONLY: True 면 시세 쓰기(수급 동기화)만 차단. 가상매매(paper) 쓰기는 영향 없음
    READONLY: bool = False

    # 데이터베이스 접속 설정 (기본값: SQLite 로컬 DB)
    DATABASE_URL: str = "sqlite:///./data/app.db"
    # 투자제안 가상매매(account_type='prop') 전용 저장소(Turso/libSQL 등).
    # 비어 있으면 'prop'도 로컬 DATABASE_URL 로 폴백한다.
    PAPER_DATABASE_URL: str = ""

    # 외부 시스템 및 디스코드 웹훅 설정
    DISCORD_WEBHOOK_URL: str = ""
    SPARK_API_SECRET_KEY: str = ""

    # 한국거래소(KRX) 로그인 정보
    KRX_ID: str = ""
    KRX_PW: str = ""

    class Config:
        """pydantic 설정 메타클래스."""
        env_file = ".env"
        env_file_encoding = "utf-8"


# 전역 설정 객체 인스턴스
settings = Settings()
