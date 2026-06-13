import os
import re
import codecs
from typing import List, Dict, Any, Tuple
from charset_normalizer import detect

# 지원하는 확장자 정의
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.wmv', '.mov', '.flv', '.webm'}
SUBTITLE_EXTENSIONS = {'.smi', '.srt', '.ass', '.vtt'}

# 로그 저장을 위한 전역 콜백 리스트 또는 단순 스트리밍을 위한 제너레이터 함수용 큐
class Logger:
    def __init__(self):
        self.listeners = []

    def subscribe(self, callback):
        self.listeners.append(callback)

    def unsubscribe(self, callback):
        if callback in self.listeners:
            self.listeners.remove(callback)

    def log(self, message: str, level: str = "INFO"):
        formatted_message = f"[{level}] {message}"
        print(formatted_message)
        for listener in self.listeners:
            try:
                listener(formatted_message)
            except Exception:
                pass

logger = Logger()

def natural_sort_key(s: str) -> List[Any]:
    """
    자릿수가 맞지 않는 에피소드 번호(예: 1, 2, ... 10)를 올바르게 정렬하기 위한 자연어 정렬 키 함수
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

# ==========================================
# SMI to SRT 파싱 및 변환 로직 (pysmi2srt 이식)
# ==========================================

def parse_smi(smi_content: str) -> List[Dict[str, Any]]:
    """
    SMI 파일 내용을 분석하여 싱크별 자막 정보 딕셔너리 리스트로 반환
    """
    def remove_tag(matchobj):
        matchtag = matchobj.group().lower()
        keep_tags = ['font', 'b', 'i', 'u']
        for keep_tag in keep_tags:
            if keep_tag in matchtag:
                return matchtag
        return ''

    def parse_p(item):
        pattern = re.compile(r'<p class=(\w+)>(.+)', flags=re.I | re.DOTALL)
        content = None
        for match in pattern.finditer(item):
            lang = match.group(1)
            content = match.group(2)
            content = content.replace('\r', '')
            content = content.replace('\n', '')
            content = re.sub('<br ?/?>', '\n', content, flags=re.I)
            content = re.sub('<[^>]+>', remove_tag, content)
        if content is None:
            content = item
            content = content.replace('\r', '')
            content = content.replace('\n', '')
            content = re.sub('<br ?/?>', '\n', content, flags=re.I)
            content = re.sub('<[^>]+>', remove_tag, content)
            
        return content

    data = []
    try:
        pattern = re.compile(r'<sync (start=\d+)\s?(end=\d+)?>', flags=re.I | re.S)
        start_end_content = pattern.split(smi_content)[1:]
        start = start_end_content[::3]
        end = start_end_content[1::3]
        content = start_end_content[2::3]
        
        for s, e, c in zip(start, end, content):
            datum = {}
            datum['start'] = int(s.split('=')[1])
            datum['end'] = int(e.split('=')[1]) if e is not None else None
            datum['content'] = parse_p(c)
            data.append(datum)
        return data
    except Exception as ex:
        logger.log(f"SMI 파싱 에러 발생: {ex}", "ERROR")
        return data

def convert_to_srt_format(data: List[Dict[str, Any]], lang: str = 'KRCC') -> str:
    """
    파싱된 자막 데이터를 SRT 포맷 텍스트로 변환
    """
    def ms_to_ts(time):
        time = int(time)
        ms = time % 1000
        s = int(time/1000) % 60
        m = int(time/1000/60) % 60
        h = int(time/1000/60/60)
        return (h, m, s, ms)

    srt = ''
    sub_nb = 1
    for i in range(len(data)-1):
        try:
            if i > 0:
                if data[i]['start'] < data[i-1]['start']:
                    continue
            if data[i]['content'] != '&nbsp;':
                srt += str(sub_nb)+'\n'
                sub_nb += 1
                if data[i]['end'] is not None:
                    srt += '%02d:%02d:%02d,%03d' % ms_to_ts(
                        data[i]['start'])+' --> '+'%02d:%02d:%02d,%03d\n' % ms_to_ts(data[i]['end'])
                else:
                    if int(data[i+1]['start']) > int(data[i]['start']):
                        srt += '%02d:%02d:%02d,%03d' % ms_to_ts(
                            data[i]['start'])+' --> '+'%02d:%02d:%02d,%03d\n' % ms_to_ts(data[i+1]['start'])
                    else:
                        srt += '%02d:%02d:%02d,%03d' % ms_to_ts(
                            data[i]['start'])+' --> '+'%02d:%02d:%02d,%03d\n' % ms_to_ts(int(data[i]['start'])+1000)
                data[i]['content'] = re.sub('&nbsp;','',data[i]['content'])
                srt += data[i]['content']+'\n\n'
        except Exception as ex:
            continue
    return srt

def convert_smi_file(smi_path: str, remove_original: bool = False, output_format: str = "srt", ignore_errors: bool = True) -> Tuple[bool, str]:
    """
    단일 SMI 자막 파일을 인코딩 자동 감지하여 UTF-8 SRT로 변환
    """
    decode_errors = 'ignore' if ignore_errors else 'strict'
    try:
        logger.log(f"자막 변환 중: {smi_path}")
        with open(smi_path, 'rb') as smi_file:
            smi_raw = smi_file.read()
            
        # 인코딩 자동 감지
        detection = detect(smi_raw)
        encoding = detection['encoding']
        if not encoding:
            encoding = 'utf-8' # 기본값
            
        logger.log(f"감지된 인코딩: {encoding} (신뢰도: {detection['confidence']})")
        
        # 디코딩
        smi_content = smi_raw.decode(encoding, errors=decode_errors)
        
        # 파싱 및 변환
        data = parse_smi(smi_content)
        srt_content = convert_to_srt_format(data)
        
        # 새 파일명 결정
        dir_name = os.path.dirname(smi_path)
        base_name = os.path.splitext(os.path.basename(smi_path))[0]
        
        if output_format == "ko.srt":
            new_filename = f"{base_name}.ko.srt"
        else:
            new_filename = f"{base_name}.srt"
            
        new_path = os.path.join(dir_name, new_filename)
        
        # UTF-8 파일로 쓰기
        with codecs.open(new_path, 'w', encoding='utf-8') as srt_file:
            srt_file.write(srt_content)
            
        logger.log(f"변환 완료 및 저장됨: {new_path}")
        
        # 원본 제거 옵션 처리
        if remove_original:
            os.remove(smi_path)
            logger.log(f"원본 SMI 파일 삭제됨: {smi_path}")
            
        return True, new_path
    except Exception as e:
        logger.log(f"자막 변환 실패 ({smi_path}): {e}", "ERROR")
        return False, str(e)


# ==========================================
# 자막 매칭 로직 (E.Z-Subtitles 기능 통합)
# ==========================================

def get_files_in_directory(dir_path: str) -> Tuple[List[str], List[str]]:
    """
    주어진 디렉토리 내의 동영상 파일과 자막 파일 목록을 반환 (자연어 정렬 적용)
    """
    videos = []
    subtitles = []
    try:
        for entry in os.scandir(dir_path):
            if entry.is_file():
                ext = os.path.splitext(entry.name)[1].lower()
                if ext in VIDEO_EXTENSIONS:
                    videos.append(entry.path)
                elif ext in SUBTITLE_EXTENSIONS:
                    subtitles.append(entry.path)
    except Exception as e:
        logger.log(f"디렉토리 스캔 오류 ({dir_path}): {e}", "ERROR")
        
    # 자연어 정렬 적용 (파일명 기준)
    videos.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
    subtitles.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
    
    return videos, subtitles

def scan_media_folder(root_dir: str) -> List[Dict[str, Any]]:
    """
    지정 폴더의 하위 경로를 재귀적으로 탐색하여 폴더 단위별 매칭 목록을 수집
    """
    logger.log(f"미디어 폴더 탐색 시작: {root_dir}")
    folder_match_groups = []
    
    # root_dir 자체가 유효하지 않거나 폴더가 아니면 빈 리스트 반환
    if not os.path.isdir(root_dir):
        logger.log(f"유효하지 않은 경로입니다: {root_dir}", "ERROR")
        return folder_match_groups

    # os.walk를 활용한 재귀적 탐색 (pysmi2srt 방식)
    for p, w, f in os.walk(root_dir):
        # 현재 폴더(p) 안의 파일 리스트 추출
        videos, subtitles = get_files_in_directory(p)
        
        # 동영상이나 자막이 하나라도 있으면 그룹 생성
        if videos or subtitles:
            match_pairs = []
            max_len = max(len(videos), len(subtitles))
            
            for i in range(max_len):
                video_path = videos[i] if i < len(videos) else None
                subtitle_path = subtitles[i] if i < len(subtitles) else None
                
                proposed_name = ""
                proposed_path = ""
                if video_path and subtitle_path:
                    video_base = os.path.splitext(os.path.basename(video_path))[0]
                    sub_ext = os.path.splitext(os.path.basename(subtitle_path))[1]
                    proposed_name = f"{video_base}{sub_ext}"
                    proposed_path = os.path.join(p, proposed_name)
                
                match_pairs.append({
                    "id": i,
                    "video_path": video_path,
                    "video_name": os.path.basename(video_path) if video_path else "",
                    "subtitle_path": subtitle_path,
                    "subtitle_name": os.path.basename(subtitle_path) if subtitle_path else "",
                    "proposed_name": proposed_name,
                    "proposed_path": proposed_path,
                    "status": "ready" if (video_path and subtitle_path and os.path.basename(subtitle_path) != proposed_name) else "synced" if (video_path and subtitle_path) else "unmatched"
                })
            
            # 상대 경로 표시를 위한 가공
            relative_dir = os.path.relpath(p, root_dir)
            if relative_dir == ".":
                relative_dir = "/"
                
            folder_match_groups.append({
                "dir_path": p,
                "relative_path": relative_dir,
                "matches": match_pairs
            })
            
    # 디렉토리명 기준 정렬
    folder_match_groups.sort(key=lambda x: natural_sort_key(x["dir_path"]))
    return folder_match_groups

def rename_subtitle(subtitle_path: str, proposed_path: str) -> Tuple[bool, str]:
    """
    자막 파일의 이름을 변경
    """
    try:
        if not os.path.exists(subtitle_path):
            return False, "원본 자막 파일이 존재하지 않습니다."
        
        # 새 파일이 이미 존재하며 대소문자 차이 외의 파일명일 경우 중복 에러 방지
        # (단, 동일 파일의 대소문자 변경 시 os.rename이 운영체제별로 다르게 작동할 수 있어 주의 필요)
        if os.path.exists(proposed_path) and subtitle_path.lower() != proposed_path.lower():
            return False, f"동일한 이름의 파일이 이미 존재합니다: {os.path.basename(proposed_path)}"
            
        os.rename(subtitle_path, proposed_path)
        logger.log(f"자막 동기화 성공: {os.path.basename(subtitle_path)} -> {os.path.basename(proposed_path)}")
        return True, "성공"
    except Exception as e:
        logger.log(f"자막 동기화 실패 ({os.path.basename(subtitle_path)}): {e}", "ERROR")
        return False, str(e)
