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
        # 프로그레스나 결과 JSON 메시지는 레벨 접두사를 붙이지 않고 원본 그대로 전송
        if message.startswith("[PROGRESS]") or message.startswith("[RESULT]"):
            formatted_message = message
        else:
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


def safe_natural_sort_key(s: str) -> List[Any]:
    """
    숫자로 시작하는 파일명과 문자로 시작하는 파일명이 섞여도 TypeError 없이 비교 가능한 정렬 키
    """
    return [
        (0, part) if isinstance(part, int) else (1, part)
        for part in natural_sort_key(s)
    ]


# 자막 파일명에 붙는 언어 코드 (예: "Show - 01.ko.srt", "Show - 01.KOR.srt")
LANGUAGE_SUFFIXES = {
    'ko', 'kor', 'kr',
    'en', 'eng',
    'ja', 'jpn', 'jp',
    'zh', 'zho', 'chi', 'chs', 'cht', 'sc', 'tc',
}

_LANGUAGE_SUFFIX_PATTERN = re.compile(r'\.([A-Za-z]{2,3})$')

# 회차 표기가 명확한 패턴 (우선순위 순)
EPISODE_PATTERNS = (
    re.compile(r'S(\d{1,2})\s*E(\d{1,4})(?!\d)', re.IGNORECASE),
    re.compile(r'\bE[P]?\s*(\d{1,4})(?!\d)', re.IGNORECASE),
    re.compile(r'#\s*(\d{1,4})(?!\d)'),
    re.compile(r'제\s*(\d{1,4})\s*화'),
    re.compile(r'(\d{1,4})\s*화'),
)

# 위 패턴에 걸리지 않는 파일명을 위한 마지막 수단.
# 대괄호로 감싼 해시/태그([5BBF013C])를 회차로 오인하지 않도록 제거한 뒤 검사한다.
_BRACKETED_PATTERN = re.compile(r'\[[^\]]*\]')
_NUMERIC_EPISODE_PATTERN = re.compile(r'(?<!\d)(?:^|[ _.\-\[\(])(\d{1,3})(?!\d)')


def extract_episode_number(filename: str) -> int | None:
    """
    파일명에서 회차 번호를 추출한다. 확실한 표기가 없으면 None을 반환한다.

    주의: 이 함수의 결과를 단독으로 신뢰하지 않는다.
    매칭 단계에서는 동영상/자막 양쪽에서 유일하게 추출된 경우에만 사용한다.
    """
    name = os.path.splitext(os.path.basename(filename))[0]

    for pattern in EPISODE_PATTERNS:
        match = pattern.search(name)
        if match:
            return int(match.group(match.lastindex or 1))

    masked = _BRACKETED_PATTERN.sub(' ', name)
    match = _NUMERIC_EPISODE_PATTERN.search(masked)
    if match:
        return int(match.group(1))

    return None


def build_unique_episode_map(paths: List[str]) -> Dict[int, str]:
    """
    회차 번호를 유일하게 특정할 수 있는 파일만 {회차: 경로}로 반환한다.

    회차를 추출하지 못했거나, 같은 회차로 추출된 파일이 여러 개(예: 다국어 자막)면
    해당 파일은 맵에서 제외되어 다음 매칭 단계(파일명/순서)로 넘어간다.
    """
    grouped: Dict[int, List[str]] = {}
    for file_path in paths:
        episode = extract_episode_number(file_path)
        if episode is None:
            continue
        grouped.setdefault(episode, []).append(file_path)

    return {
        episode: episode_paths[0]
        for episode, episode_paths in grouped.items()
        if len(episode_paths) == 1
    }


def get_stem_key(path: str) -> str:
    """
    확장자와 언어 코드를 제거한 비교용 파일명 키
    (예: "Show - 01.ko.srt" -> "show - 01")
    """
    stem = os.path.splitext(os.path.basename(path))[0]
    for _ in range(2):  # "Show.01.ko" 처럼 언어 코드가 겹치는 경우 대비
        match = _LANGUAGE_SUFFIX_PATTERN.search(stem)
        if not match or match.group(1).lower() not in LANGUAGE_SUFFIXES:
            break
        stem = stem[:match.start()]
    return stem.strip().lower()

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

# 매칭 근거 (UI 표시 및 디버깅용)
MATCH_METHOD_BASENAME = "basename"   # 확장자/언어 코드만 다른 동일 파일명
MATCH_METHOD_EPISODE = "episode"     # 양쪽 모두 유일하게 추출된 회차 번호
MATCH_METHOD_ORDER = "order"         # 남은 파일끼리 자연어 정렬 순서


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

def _get_subtitle_lang_suffix(path: str) -> str:
    """
    자막 파일명에 붙은 언어 코드 접미사를 반환한다. (예: "Show - 01.ko.srt" -> ".ko")
    """
    stem = os.path.splitext(os.path.basename(path))[0]
    match = _LANGUAGE_SUFFIX_PATTERN.search(stem)
    if match and match.group(1).lower() in LANGUAGE_SUFFIXES:
        return match.group(0)
    return ""


def _build_proposed_name(video_path: str, subtitle_path: str) -> str:
    """
    동영상 파일명 기준의 자막 제안 이름.
    언어 코드(.ko, .en 등)는 유지하여 같은 회차의 다국어 자막이 서로 덮어쓰지 않게 한다.
    """
    video_base = os.path.splitext(os.path.basename(video_path))[0]
    lang_suffix = _get_subtitle_lang_suffix(subtitle_path)
    sub_ext = os.path.splitext(os.path.basename(subtitle_path))[1]
    return f"{video_base}{lang_suffix}{sub_ext}"


def _row_sort_key(row: Dict[str, Any]) -> List[Any]:
    """
    동영상이 있는 행을 파일명 순으로 먼저, 동영상이 없는(자막만 있는) 행을 뒤로 정렬.
    같은 동영상에 자막이 여러 개면 자막 파일명 순으로 정렬한다.
    """
    if row["video_path"]:
        return (
            0,
            safe_natural_sort_key(os.path.basename(row["video_path"])),
            safe_natural_sort_key(row["subtitle_name"]),
        )
    return (1, [], safe_natural_sort_key(row["subtitle_name"]))


def _make_match_pair(
    directory: str,
    video_path: str | None,
    subtitle_path: str | None,
    method: str,
) -> Dict[str, Any]:
    """
    매칭 결과 한 행(동영상/자막 쌍)을 생성한다.
    하나의 동영상에 여러 자막(.smi, .srt 등)이 연결될 수 있다.
    """
    proposed_name = ""
    proposed_path = ""
    if video_path and subtitle_path:
        proposed_name = _build_proposed_name(video_path, subtitle_path)
        proposed_path = os.path.join(directory, proposed_name)
        status = "synced" if os.path.basename(subtitle_path) == proposed_name else "ready"
        match_method = method
    else:
        status = "unmatched"
        match_method = "unmatched"

    return {
        "id": 0,
        "video_path": video_path,
        "video_name": os.path.basename(video_path) if video_path else "",
        "subtitle_path": subtitle_path,
        "subtitle_name": os.path.basename(subtitle_path) if subtitle_path else "",
        "proposed_name": proposed_name,
        "proposed_path": proposed_path,
        "status": status,
        "match_method": match_method,
    }


def build_match_pairs(directory: str, videos: List[str], subtitles: List[str]) -> List[Dict[str, Any]]:
    """
    한 폴더의 동영상/자막을 다음 3단계로 매칭한다.

      1) 확장자/언어 코드만 다른 동일 파일명                 (가장 확실)
      2) 동영상 쪽에서 유일하게 추출된 회차 번호              (신뢰도 높음)
      3) 남은 파일끼리 자연어 정렬 순서 1:1                   (main 브랜치의 기존 동작)

    동영상 1개에 자막 여러 개(.smi + .srt + .ko.srt 등)가 붙을 수 있다.
    각 단계는 "아직 매칭되지 않고 남은 자막"만 대상으로 삼으므로,
    어느 한 단계에서 한쪽만 인식되더라도 파일이 고립되지 않는다.
    """
    remaining_videos = sorted(videos, key=lambda x: natural_sort_key(os.path.basename(x)))
    remaining_subtitles = sorted(subtitles, key=lambda x: natural_sort_key(os.path.basename(x)))
    pairs: List[Tuple[str | None, str | None, str]] = []
    matched_videos: set = set()  # 자막이 하나라도 연결된 동영상

    # 1단계: 언어 코드만 다른 동일 파일명 (예: "Show - 01.mkv" <-> "Show - 01.ko.srt")
    exact_video_by_stem: Dict[str, str] = {}
    video_by_stem_key: Dict[str, str] = {}
    for video_path in remaining_videos:
        stem = os.path.splitext(os.path.basename(video_path))[0].strip().lower()
        exact_video_by_stem.setdefault(stem, video_path)
        video_by_stem_key.setdefault(get_stem_key(video_path), video_path)

    for subtitle_path in list(remaining_subtitles):
        subtitle_stem = os.path.splitext(os.path.basename(subtitle_path))[0].strip().lower()
        video_path = exact_video_by_stem.get(subtitle_stem)
        if not video_path:
            video_path = video_by_stem_key.get(get_stem_key(subtitle_path))
        if not video_path:
            continue
        pairs.append((video_path, subtitle_path, MATCH_METHOD_BASENAME))
        matched_videos.add(video_path)
        remaining_subtitles.remove(subtitle_path)

    # 2단계: 회차 번호 — 동영상은 회차별로 유일해야 하고, 자막은 여러 개 허용
    video_by_episode = build_unique_episode_map(remaining_videos)
    subtitle_by_episode: Dict[int, List[str]] = {}
    for subtitle_path in remaining_subtitles:
        episode = extract_episode_number(subtitle_path)
        if episode is not None:
            subtitle_by_episode.setdefault(episode, []).append(subtitle_path)

    for episode in sorted(set(video_by_episode) & set(subtitle_by_episode)):
        video_path = video_by_episode[episode]
        episode_subtitles = sorted(
            subtitle_by_episode[episode],
            key=lambda x: natural_sort_key(os.path.basename(x)),
        )
        for subtitle_path in episode_subtitles:
            pairs.append((video_path, subtitle_path, MATCH_METHOD_EPISODE))
            remaining_subtitles.remove(subtitle_path)
        matched_videos.add(video_path)

    # 3단계: 아직 자막이 없는 동영상과 남은 자막을 자연어 정렬 순서대로 1:1 대응
    leftover_videos = [video_path for video_path in remaining_videos if video_path not in matched_videos]
    max_len = max(len(leftover_videos), len(remaining_subtitles))
    for i in range(max_len):
        video_path = leftover_videos[i] if i < len(leftover_videos) else None
        subtitle_path = remaining_subtitles[i] if i < len(remaining_subtitles) else None
        pairs.append((video_path, subtitle_path, MATCH_METHOD_ORDER))

    # 안전장치: 양쪽에 파일이 있는데 매칭된 쌍이 하나도 없다면 순서 기반으로 재시도한다.
    # (향후 매칭 로직이 변경되어도 "조용히 0건"으로 끝나는 상황을 만들지 않기 위함)
    if videos and subtitles and not any(video and subtitle for video, subtitle, _ in pairs):
        logger.log(
            f"경고: 매칭된 쌍이 없어 순서 기반 매칭으로 대체합니다. ({directory})",
            "WARN",
        )
        ordered_videos = sorted(videos, key=lambda x: natural_sort_key(os.path.basename(x)))
        ordered_subtitles = sorted(subtitles, key=lambda x: natural_sort_key(os.path.basename(x)))
        pairs = [
            (
                ordered_videos[i] if i < len(ordered_videos) else None,
                ordered_subtitles[i] if i < len(ordered_subtitles) else None,
                MATCH_METHOD_ORDER,
            )
            for i in range(max(len(ordered_videos), len(ordered_subtitles)))
        ]

    rows = [
        _make_match_pair(directory, video_path, subtitle_path, method)
        for video_path, subtitle_path, method in pairs
    ]
    rows.sort(key=_row_sort_key)

    # 같은 경로로 이름이 겹치는 자막은 자동 변경하지 않는다.
    # (예: 언어 코드가 없는 같은 확장자 자막 2개 -> 한쪽이 조용히 실패하는 것을 방지)
    claims: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        if row["proposed_path"]:
            claims.setdefault(row["proposed_path"].lower(), []).append(row)

    for target_path, claimed_rows in claims.items():
        if len(claimed_rows) < 2:
            continue
        already_synced = [row for row in claimed_rows if row["subtitle_name"] == row["proposed_name"]]
        losers = [row for row in claimed_rows if row is not already_synced[0]] if len(already_synced) == 1 else claimed_rows
        for row in losers:
            row["status"] = "conflict"
            row["proposed_name"] = ""
            row["proposed_path"] = ""
        logger.log(
            f"경고: 같은 이름으로 변경될 자막이 있어 자동 변경에서 제외했습니다: "
            f"{os.path.basename(target_path)} ({directory})",
            "WARN",
        )

    for index, row in enumerate(rows):
        row["id"] = index

    # 순서로 이어붙였는데 양쪽 회차가 서로 다르면 잘못된 이름 변경일 수 있으므로 경고한다.
    conflicting = 0
    for row in rows:
        if row["match_method"] != MATCH_METHOD_ORDER:
            continue
        video_episode = extract_episode_number(row["video_path"]) if row["video_path"] else None
        subtitle_episode = extract_episode_number(row["subtitle_path"]) if row["subtitle_path"] else None
        if video_episode is not None and subtitle_episode is not None and video_episode != subtitle_episode:
            conflicting += 1
    if conflicting:
        logger.log(
            f"경고: 회차가 서로 다른 파일을 순서로 매칭했습니다 {conflicting}건. "
            f"미리보기에서 반드시 확인하세요. ({directory})",
            "WARN",
        )

    return rows


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
            match_pairs = build_match_pairs(p, videos, subtitles)

            # 상대 경로 표시를 위한 가공
            relative_dir = os.path.relpath(p, root_dir)
            if relative_dir == ".":
                relative_dir = "/"

            # 미매칭이 남아 있으면 원인 파악이 가능하도록 요약 로그를 남긴다.
            unmatched_count = sum(1 for row in match_pairs if row["status"] == "unmatched")
            if unmatched_count:
                logger.log(
                    f"[{relative_dir}] 미매칭 {unmatched_count}건 "
                    f"(동영상 {len(videos)}개 / 자막 {len(subtitles)}개)",
                    "WARN",
                )

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
