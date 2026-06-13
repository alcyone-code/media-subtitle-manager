# Media Subtitle Manager (미디어 자막 관리 시스템)

본 프로젝트는 Synology NAS Docker 환경에서 동작하는 웹 기반 자막 관리 솔루션입니다.  
기존에 신뢰성 있게 동작해 온 **E.Z-Subtitles**(자연어 자막 매칭)의 정렬 로직과 **pysmi2srt**(SMI ➡️ SRT 변환)의 정제 및 싱크 변환 알고리즘을 하나로 통합하여 미려한 웹 GUI 대시보드로 제공합니다.

---

## 🌟 주요 기능

### 1. 폴더 단위 격리 자막 매칭 (E.Z-Subtitles 기능 계승)
- **재귀적 파일 탐색**: 하위 경로를 순회하며 동영상과 자막 파일들을 자동 수집합니다.
- **시즌 폴더 격리 매칭**: 불필요한 전체 파일 매칭 대신, 동영상과 자막이 있는 각 디렉토리 단위로 독립(격리)하여 1:1 정렬 매칭을 수행합니다. 시즌 1과 시즌 2의 파일들이 뒤섞이지 않습니다.
- **자연어 정렬 (Natural Sort)**: 에피소드 번호 자릿수(예: `1, 2` vs `10`)가 맞춰지지 않은 경우에도 정렬이 꼬이지 않도록 커스텀 자연어 정렬 알고리즘(`natural_sort_key`)을 사용하여 자막과 동영상을 정확하게 매칭합니다.
- **드래그 앤 드롭 형태의 수동 순서 조절**: 웹 GUI에서 자막 행의 순서를 ▲/▼ 버튼으로 수동 조절(Swap)할 수 있어 미세한 매칭 어긋남을 쉽게 바로잡을 수 있습니다.

### 2. SMI to SRT 일괄 변환 (pysmi2srt 기능 통합)
- **인코딩 자동 감지**: `charset-normalizer`를 통해 EUC-KR, CP949 등 다양한 한국어 자막 인코딩을 자동 감지하여 한글 깨짐 현상 없이 UTF-8 기반 SRT 자막을 생성합니다.
- **자막 싱크 및 태그 정제**: 기존 HTML 태그 정제 로직(허용된 폰트, 볼드, 이탤릭, 언더라인 외 태그 삭제) 및 밀리초 ➡️ 타임스탬프 싱크 연산 규칙을 완벽 보존하였습니다.
- **원본 삭제 옵션**: 변환 성공 시 원본 SMI 자막을 삭제할지 여부를 선택할 수 있습니다.

### 3. 실시간 로그 출력 및 제어 패널 (Web Dashboard)
- **폴더 브라우저**: 마운트된 미디어 폴더의 디렉토리 구조를 직관적으로 탐색 및 선택할 수 있습니다.
- **실시간 터미널 로그**: 백엔드에서 수행되는 매칭 및 변환 로그를 **SSE (Server-Sent Events)** 기술을 이용해 브라우저 화면의 미려한 가상 콘솔 창에 실시간으로 출력합니다.

---

## 📁 디렉토리 구조

```
media-subtitle-manager/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py            # FastAPI API 서버 진입점 및 라우팅
│   │   ├── subtitle_utils.py  # 핵심 자막 매칭 및 SMI 변환 유틸리티 모듈
│   │   └── static/            # 프론트엔드 웹 대시보드 리소스
│   │       ├── index.html     # 메인 HTML 마크업
│   │       ├── style.css      # 다크 글래스모피즘 테마 스타일시트
│   │       └── app.js         # API 통신, 테이블 렌더링, 스왑 조절, SSE 리스너
│   └── requirements.txt       # 의존성 라이브러리 (FastAPI, Uvicorn, charset-normalizer)
├── Dockerfile                 # 경량화 빌드 및 gosu 권한 셋업용
├── entrypoint.sh              # PUID/PGID 기반 동적 권한 매핑 스크립트
└── docker-compose.yml         # Synology NAS 배포용 컴포즈 규격
```

---

## 🚀 Docker 배포 및 실행 방법 (Synology NAS 최적화)

Synology NAS 환경에서 파일 시스템 쓰기 및 이름 변경 권한 충돌이 나지 않도록 실행 권한(`PUID`/`PGID`)을 환경변수로 넘겨받아 안전하게 처리합니다.

### 1. 사용자 ID 확인
DSM의 SSH 터미널에 접속하여 컨테이너를 구동하고 파일을 수정할 사용자의 UID와 GID를 확인합니다.
```bash
id username
# 출력 예시: uid=1026(username) gid=100(users)
```

### 2. 설정 수정 (`docker-compose.yml`)
`docker-compose.yml`을 편집하여 확인한 권한 값과 비디오 폴더 절대 경로를 설정합니다.
```yaml
environment:
  - PUID=1026   # 본인의 UID로 변경
  - PGID=100    # 본인의 GID로 변경
volumes:
  - /volume1/video:/media  # 실제 NAS의 미디어 디렉토리 절대경로를 /media에 바인딩
```

### 3. 컨테이너 빌드 및 실행
프로젝트 루트 폴더로 이동한 후 다음 명령어를 실행합니다.
```bash
docker-compose up -d --build
```
이후 웹 브라우저를 통해 `http://<NAS_IP>:8080`에 접속하면 시스템 대시보드를 사용할 수 있습니다.

---

## 🛠️ 개발자 가이드 및 검증

### 1. 백엔드 로컬 실행 및 의존성 설치
로컬에서 테스트 서버를 가동하여 API 응답 상태를 확인해볼 수 있습니다.
```bash
# 의존성 패키지 설치
pip install -r backend/requirements.txt

# FastAPI 서버 가동
PYTHONPATH=./backend uvicorn app.main:app --host 127.0.0.1 --port 8080
```

### 2. 자동화 테스트 수행
자연어 정렬, SMI 파싱 및 타이밍 변환, 디렉토리 스캔 매칭 등의 핵심 비즈니스 로직들이 정상 동작하는지 테스트 스크립트를 통해 검증할 수 있습니다.
```bash
PYTHONPATH=./backend python3 test_subtitles.py
```
*(성공 시 콘솔에 "모든 유닛 테스트가 성공했습니다!" 라는 출력과 함께 테스트 디렉토리가 자동으로 클린업됩니다.)*
