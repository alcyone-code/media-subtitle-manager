#!/bin/bash
set -e

# PUID/PGID 환경변수가 없으면 기본값 1000 사용
PUID=${PUID:-1000}
PGID=${PGID:-1000}

USER_NAME="mediauser"
GROUP_NAME="mediagroup"

echo "Permissions initialization: PUID=${PUID}, PGID=${PGID}"

# 그룹이 이미 존재하지 않으면 생성, 있으면 GID 변경
if ! getent group "$GROUP_NAME" >/dev/null; then
    groupadd -o -g "$PGID" "$GROUP_NAME"
else
    groupmod -o -g "$PGID" "$GROUP_NAME"
fi

# 유저가 존재하지 않으면 생성, 있으면 UID 변경
if ! getent passwd "$USER_NAME" >/dev/null; then
    useradd -o -u "$PUID" -g "$GROUP_NAME" -m -s /bin/bash "$USER_NAME"
else
    usermod -o -u "$PUID" -g "$GROUP_NAME" "$USER_NAME"
fi

# /app 폴더 소유권 조정
chown -R "$USER_NAME":"$GROUP_NAME" /app

# 기본 미디어 폴더(/media)가 볼륨 바인딩 시 권한 수정을 원할 경우 수행
# Synology 마운트 경로에 맞춤 권한 부여
if [ -d "/media" ]; then
    echo "Media folder found. Setting owner..."
    # 전체 하위 재귀 소유권 변경은 미디어 라이브러리가 클 경우 부하를 줄 수 있으므로
    # 디렉토리 자체 소유권만 설정하거나 생략 가능. 여기서는 디렉토리 수준만 처리
    chown "$USER_NAME":"$GROUP_NAME" /media || true
fi

echo "Running application with $USER_NAME..."

# gosu를 이용하여 동적으로 생성/매핑된 유저 권한으로 uvicorn 백엔드 시작
exec gosu "$USER_NAME" "$@"
