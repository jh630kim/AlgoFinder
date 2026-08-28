# AlgoFinder 웹(Koyeb) 배포 이미지 — APP_PROFILE=web, 읽기 전용, 경량 1년치 DB 내장.
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# 경량 서빙 의존성만 설치
COPY deploy/requirements-web.txt ./requirements-web.txt
RUN pip install --no-cache-dir -r requirements-web.txt

# 앱 소스
COPY . .

# 빌드 시 GitHub Release에서 최신 경량 DB를 받아 이미지에 굽는다(URL은 빌드 인자).
# 예: --build-arg LITE_DB_URL="https://github.com/<owner>/<repo>/releases/download/lite-db/app_lite.db"
ARG LITE_DB_URL=""
RUN mkdir -p data \
    && if [ -n "$LITE_DB_URL" ]; then curl -fSL "$LITE_DB_URL" -o data/app_lite.db; \
       else echo "LITE_DB_URL 미지정 — data/app_lite.db 가 소스에 포함돼 있어야 함"; fi

ENV APP_PROFILE=web \
    READONLY=1 \
    FLASK_DEBUG=False \
    DATABASE_URL=sqlite:///./data/app_lite.db \
    PORT=8000

EXPOSE 8000

# Koyeb이 $PORT를 주입한다. gunicorn으로 app:app 구동.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120 app:app"]
