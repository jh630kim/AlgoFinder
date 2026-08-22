"""
API 패키지 모듈.

Flask API 블루프린트 객체를 가져와 플라스크 앱에 간편히 등록합니다.
"""

from backend.app.api.routes import api_bp
from backend.app.api.routes_paper import paper_api_bp

__all__ = ["api_bp", "paper_api_bp"]
