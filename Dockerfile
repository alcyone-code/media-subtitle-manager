FROM python:3.10-slim

# 필요한 패키지 설치 (gosu, shadow - PUID/PGID 처리를 위함)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gosu \
    passwd \
    && rm -rf /var/lib/apt/lists/*

# 앱 디렉토리 생성
WORKDIR /app

# 라이브러리 설치를 위한 requirements.txt 복사 및 설치
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 소스 복사
COPY backend/app/ ./app/

# 엔트리포인트 셸 스크립트 복사 및 실행 권한 부여
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Synology NAS 미디어 볼륨 기본 경로 생성
RUN mkdir -p /media

# 8080 포트 노출
EXPOSE 8080

# 엔트리포인트 지정
ENTRYPOINT ["/entrypoint.sh"]

# 기본 실행 커맨드 지정
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
