import os
import json
import asyncio
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
from app.subtitle_utils import (
    logger,
    scan_media_folder,
    rename_subtitle,
    convert_smi_file,
    VIDEO_EXTENSIONS,
    SUBTITLE_EXTENSIONS
)

app = FastAPI(title="Media 자막 관리 시스템")
APP_VERSION = os.environ.get("APP_VERSION", "dev")

# 기본 미디어 디렉토리 경로 (Synology NAS 마운트 경로 대응)
DEFAULT_MEDIA_DIR = "/media"

# Pydantic 모델 정의
class PathRequest(BaseModel):
    path: str

class MatchItem(BaseModel):
    subtitle_path: str
    proposed_path: str

class MatchExecuteRequest(BaseModel):
    targets: List[MatchItem]

class ConvertRequest(BaseModel):
    path: str
    remove_original: bool = False
    output_format: str = "srt"  # "srt" 또는 "ko.srt"
    ignore_errors: bool = True


# API: 폴더 구조 탐색
@app.get("/api/browse")
def browse_directory(path: Optional[str] = None):
    target_path = path if path else DEFAULT_MEDIA_DIR
    
    # 보안: 시스템 루트 밖이나 비정상적인 디렉토리 접근 제어
    if not os.path.exists(target_path):
        # 만약 /media가 존재하지 않는 개발 환경(예: 로컬 개발)일 경우, 현재 작업 경로를 기본값으로 사용
        if target_path == DEFAULT_MEDIA_DIR:
            target_path = os.getcwd()
        else:
            raise HTTPException(status_code=404, detail="지정한 경로가 존재하지 않습니다.")
            
    if not os.path.isdir(target_path):
        raise HTTPException(status_code=400, detail="지정한 경로는 디렉토리가 아닙니다.")
        
    try:
        directories = []
        files = []
        
        # 상위 디렉토리 결정
        parent_path = os.path.dirname(target_path)
        if target_path == "/" or target_path == parent_path:
            parent_path = ""
            
        for entry in os.scandir(target_path):
            if entry.is_dir():
                # 숨김 폴더 및 점(.)으로 시작하는 폴더 제외
                if not entry.name.startswith('.'):
                    directories.append({
                        "name": entry.name,
                        "path": entry.path
                    })
            elif entry.is_file():
                if not entry.name.startswith('.'):
                    ext = os.path.splitext(entry.name)[1].lower()
                    is_video = ext in VIDEO_EXTENSIONS
                    is_subtitle = ext in SUBTITLE_EXTENSIONS
                    
                    try:
                        size = entry.stat().st_size
                    except Exception:
                        size = 0
                        
                    files.append({
                        "name": entry.name,
                        "path": entry.path,
                        "size": size,
                        "is_video": is_video,
                        "is_subtitle": is_subtitle
                    })
                    
        # 가나다/알파벳 순서로 정렬
        directories.sort(key=lambda x: x["name"].lower())
        files.sort(key=lambda x: x["name"].lower())
        
        return {
            "current_path": target_path,
            "parent_path": parent_path,
            "directories": directories,
            "files": files
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"디렉토리 읽기 실패: {str(e)}")


# API: 자막 매칭 미리보기
@app.post("/api/match/preview")
def preview_matches(req: PathRequest):
    if not os.path.exists(req.path):
        raise HTTPException(status_code=404, detail="지정한 경로가 존재하지 않습니다.")
    try:
        logger.log(f"매칭 미리보기 스캔 시작: {req.path}")
        results = scan_media_folder(req.path)
        logger.log(f"매칭 미리보기 스캔 완료. 탐색된 폴더 수: {len(results)}")
        return results
    except Exception as e:
        logger.log(f"미리보기 실패: {e}", "ERROR")
        raise HTTPException(status_code=500, detail=str(e))


# API: 자막 매칭 실행 (파일명 변경)
@app.post("/api/match/execute")
def execute_matches(req: MatchExecuteRequest):
    success_count = 0
    fail_count = 0
    failures = []
    
    logger.log(f"자막 파일명 동기화 실행 시작. 대상 파일 수: {len(req.targets)}")
    
    for item in req.targets:
        success, message = rename_subtitle(item.subtitle_path, item.proposed_path)
        if success:
            success_count += 1
        else:
            fail_count += 1
            failures.append({
                "source": item.subtitle_path,
                "target": item.proposed_path,
                "error": message
            })
            
    logger.log(f"동기화 완료. 성공: {success_count}개, 실패: {fail_count}개")
    return {
        "success": True,
        "success_count": success_count,
        "fail_count": fail_count,
        "failures": failures
    }


# 비동기 SMI 변환 작업 처리 함수
def run_bulk_conversion(path: str, remove_original: bool, output_format: str, ignore_errors: bool):
    logger.log(f"자막 일괄 변환 작업 시작. 대상 디렉토리: {path}")
    
    if not os.path.isdir(path):
        logger.log(f"유효하지 않은 디렉토리 경로입니다: {path}", "ERROR")
        return

    # 1단계: 변환 대상 SMI 자막 파일 모두 수집
    smi_files = []
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.lower().endswith('.smi'):
                smi_files.append(os.path.join(root, file))

    total_count = len(smi_files)
    if total_count == 0:
        logger.log("변환할 SMI 파일이 없습니다.")
        logger.log(f"[RESULT] " + json.dumps({"success_count": 0, "fail_count": 0, "failures": []}, ensure_ascii=False))
        return

    logger.log(f"총 {total_count}개의 SMI 파일을 변환합니다.")

    success_files = []
    fail_files = []
    current_count = 0

    # 2단계: 순회하며 변환 진행 및 프로그레스 로깅
    for full_path in smi_files:
        current_count += 1
        file_name = os.path.basename(full_path)
        
        success, new_path_or_err = convert_smi_file(
            full_path, 
            remove_original=remove_original, 
            output_format=output_format,
            ignore_errors=ignore_errors
        )
        
        if success:
            success_files.append(file_name)
        else:
            fail_files.append({"path": full_path, "file": file_name, "error": new_path_or_err})
            
        # 진행률 전송
        progress_data = {
            "total": total_count,
            "current": current_count,
            "success": len(success_files),
            "fail": len(fail_files),
            "current_file": file_name
        }
        logger.log(f"[PROGRESS] " + json.dumps(progress_data, ensure_ascii=False))

    logger.log(f"자막 일괄 변환 작업 완료. 성공: {len(success_files)}개, 실패: {len(fail_files)}개")
    
    # 결과 요약 전송
    result_data = {
        "success_count": len(success_files),
        "fail_count": len(fail_files),
        "failures": fail_files
    }
    logger.log(f"[RESULT] " + json.dumps(result_data, ensure_ascii=False))


# API: 자막 일괄 변환 (SMI -> SRT)
@app.post("/api/convert")
def convert_subtitles(req: ConvertRequest, background_tasks: BackgroundTasks):
    if not os.path.exists(req.path):
        raise HTTPException(status_code=404, detail="지정한 경로가 존재하지 않습니다.")
        
    # 백그라운드 태스크에 대량의 일괄 변환 태스크 등록
    background_tasks.add_task(
        run_bulk_conversion,
        req.path,
        req.remove_original,
        req.output_format,
        req.ignore_errors
    )
    
    return {
        "success": True,
        "message": "자막 일괄 변환이 백그라운드에서 예약되었습니다. 실시간 로그 창에서 진행 상태를 확인하세요."
    }


# API: 실시간 로그 스트리밍 (SSE)
@app.get("/api/logs/stream")
async def stream_logs(request: Request):
    # 비동기 메인 이벤트 루프를 호출 시점에 안전하게 캡처
    loop = asyncio.get_running_loop()

    async def log_generator():
        # 로그 대기 큐 생성
        queue = asyncio.Queue()
        
        # 콜백 리스너 등록
        def listener(msg):
            # 캡처한 메인 루프를 통해 스레드 안전하게 항목 추가
            loop.call_soon_threadsafe(queue.put_nowait, msg)
            
        logger.subscribe(listener)
        
        try:
            while True:
                # 클라이언트가 연결 해제되었는지 수시로 체크
                if await request.is_disconnected():
                    break
                try:
                    # 1.5초 이내에 로그가 들어오면 내보냄
                    msg = await asyncio.wait_for(queue.get(), timeout=1.5)
                    # 데이터 전송 포맷 (SSE 스펙: "data: <content>\n\n")
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    # 연결 끊김을 막기 위해 Keep-Alive 전송
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            logger.unsubscribe(listener)
            
    return StreamingResponse(log_generator(), media_type="text/event-stream")

# API: 앱 버전 조회
@app.get("/api/version")
def get_version():
    return {"version": APP_VERSION}


static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
