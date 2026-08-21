"""
시스템 환경 설정 관리 모듈.

이 모듈은 `.env` 파일 및 환경 변수로부터 DB 접속 정보, API 키 등
시스템 전역 설정을 로드하고 관리하는 역할을 전담합니다.
"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    시스템 전역 환경 변수 설정 클래스.

    pydantic-settings를 사용하여 환경 변수를 검증하고 로드합니다.
    """
    APP_NAME: str = "AlgoFinder"
    ENV: str = "development"
    
    # 데이터베이스 접속 설정 (기본값: SQLite 로컬 DB)
    DATABASE_URL: str = "sqlite:///./data/app.db"
    
    # 외부 시스템 및 디스코드 웹훅 설정
    DISCORD_WEBHOOK_URL: str = ""
    SPARK_API_SECRET_KEY: str = ""

    class Config:
        """pydantic 설정 메타클래스."""
        env_file = ".env"
        env_file_encoding = "utf-8"


# 전역 설정 객체 인스턴스
settings = Settings()
