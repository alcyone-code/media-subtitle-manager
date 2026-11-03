"""
자막 파일명 자동매칭 회귀 테스트

핵심 원칙
---------
1) 동영상/자막 양쪽에서 회차를 "유일하게" 추출했을 때만 회차 기반 매칭을 사용한다.
2) 어떤 경우에도 파일이 고립되어 "0건 매칭"으로 끝나지 않는다. (마지막 단계는 순서 기반)
3) 한 파일은 결과에서 정확히 한 번만 등장한다.
"""

import os
import re

import pytest

from subtitle_utils import (
    build_match_pairs,
    build_unique_episode_map,
    extract_episode_number,
    get_stem_key,
    scan_media_folder,
)


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def create_files(directory, names):
    for name in names:
        (directory / name).write_text("", encoding="utf-8")


def flatten(groups):
    return [row for group in groups for row in group["matches"]]


def assert_invariants(rows, videos, subtitles):
    """모든 파일이 정확히 한 번씩 등장하고, 중복 매칭이 없어야 한다."""
    used_videos = [os.path.basename(row["video_path"]) for row in rows if row["video_path"]]
    used_subtitles = [os.path.basename(row["subtitle_path"]) for row in rows if row["subtitle_path"]]

    assert len(used_videos) == len(set(used_videos)), "동영상이 중복 매칭되었습니다"
    assert len(used_subtitles) == len(set(used_subtitles)), "자막이 중복 매칭되었습니다"
    assert sorted(videos) == sorted(used_videos), "동영상 누락/추가 발생"
    assert sorted(subtitles) == sorted(used_subtitles), "자막 누락/추가 발생"


def assert_never_zero_match(rows, videos, subtitles):
    """양쪽에 파일이 있는데 매칭된 쌍이 0건이면 실패 (이번 사고의 핵심 증상)."""
    if videos and subtitles:
        matched = [row for row in rows if row["video_path"] and row["subtitle_path"]]
        assert matched, "동영상/자막이 모두 존재하지만 매칭된 쌍이 0건입니다"


# ---------------------------------------------------------------------------
# 회차 추출 단위 테스트
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "filename, expected",
    [
        ("Show S01E07 1080p.mkv", 7),
        ("Show EP12.mkv", 12),
        ("Show #03 [1080p].mkv", 3),
        ("Show 제08화.smi", 8),
        ("Show 09화 720p.smi", 9),
        ("Show - 01 [720p NF WEB-DL].mkv", 1),
        # 실제 사고 파일: 숫자 뒤에 구분자가 아니라 문자가 붙는 형태
        ("Kaoru Hana wa Rin to Saku - 01Erai.smi", 1),
        ("Show - 05v2.smi", 5),
        ("Show - 01.ko.srt", 1),
        # 연도/해상도는 회차로 오인하면 안 된다
        ("Show (2021) - 05.mkv", 5),
        ("Show.2021.1080p.mkv", None),
        # 대괄호 안의 해시 값은 회차가 아니다
        ("[5BBF013C] Show.mkv", None),
        ("[Erai-raws] Show [ABC123].mkv", None),
    ],
)
def test_extract_episode_number(filename, expected):
    assert extract_episode_number(filename) == expected


def test_unique_episode_map_excludes_unknown_and_duplicate():
    paths = [
        "Show - 01.mkv",
        "Show - 02.mkv",
        "Show - 02.ko.srt",   # 같은 회차 중복 -> 둘 다 제외
        "Show - 03.en.srt",   # 유일한 3화 -> 포함
        "Show - special.smi",  # 회차 없음 -> 제외
    ]
    assert build_unique_episode_map(paths) == {
        1: "Show - 01.mkv",
        3: "Show - 03.en.srt",
    }


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("Show - 01.ko.srt", "show - 01"),
        ("Show - 01.KOR.srt", "show - 01"),
        ("Show - 01.en.srt", "show - 01"),
        ("Show - 01.mkv", "show - 01"),
        ("Show - 01.srt", "show - 01"),
    ],
)
def test_get_stem_key_strips_language_suffix(filename, expected):
    assert get_stem_key(filename) == expected


# ---------------------------------------------------------------------------
# 실제 사고 재현: Erai-raws 동영상 + "01Erai.smi" 자막
# ---------------------------------------------------------------------------

def test_erai_raws_incident_regression(tmp_path):
    videos = [
        f"[Erai-raws] Kaoru Hana wa Rin to Saku - {n:02d} "
        f"[720p NF WEB-DL AVC AAC][MultiSub][{n:08X}].mkv"
        for n in range(1, 14)
    ]
    subtitles = [f"Kaoru Hana wa Rin to Saku - {n:02d}Erai.smi" for n in range(1, 14)]
    create_files(tmp_path, videos + subtitles)

    groups = scan_media_folder(str(tmp_path))
    rows = flatten(groups)

    assert len(groups) == 1
    assert len(rows) == 13
    assert sum(row["status"] == "ready" for row in rows) == 13
    assert all(row["match_method"] == "episode" for row in rows)
    assert_never_zero_match(rows, videos, subtitles)
    assert_invariants(rows, videos, subtitles)

    # 회차가 서로 어긋나지 않았는지 확인
    for row in rows:
        video_ep = int(re.search(r"- (\d{2}) \[", row["video_name"]).group(1))
        subtitle_ep = int(re.search(r"- (\d{2})Erai", row["subtitle_name"]).group(1))
        assert video_ep == subtitle_ep
        assert row["proposed_name"] == row["video_name"].replace(".mkv", ".smi")


def test_episode_matching_ignores_file_list_order(tmp_path):
    videos = ["Show - 02.mkv", "Show - 01.mkv", "Show - 03.mkv"]
    subtitles = ["Show - 03Sub.smi", "Show - 01Sub.smi", "Show - 02Sub.smi"]

    rows = build_match_pairs(str(tmp_path), videos, subtitles)

    assert_invariants(rows, videos, subtitles)
    assert all(row["match_method"] == "episode" for row in rows)
    for row in rows:
        video_ep = re.search(r"- (\d{2})\.mkv$", row["video_name"]).group(1)
        subtitle_ep = re.search(r"- (\d{2})Sub\.smi$", row["subtitle_name"]).group(1)
        assert video_ep == subtitle_ep


# ---------------------------------------------------------------------------
# 기존(main) 동작 보존: 순서 기반 매칭
# ---------------------------------------------------------------------------

def test_identical_names_are_synced(tmp_path):
    videos = ["Show - 01.mkv", "Show - 02.mkv"]
    subtitles = ["Show - 01.srt", "Show - 02.srt"]
    create_files(tmp_path, videos + subtitles)

    rows = flatten(scan_media_folder(str(tmp_path)))

    assert_invariants(rows, videos, subtitles)
    assert {row["status"] for row in rows} == {"synced"}
    assert {row["match_method"] for row in rows} == {"basename"}


def test_language_suffix_subtitle_is_renamed(tmp_path):
    videos = ["Show - 01.mkv"]
    subtitles = ["Show - 01.ko.srt"]
    create_files(tmp_path, videos + subtitles)

    rows = flatten(scan_media_folder(str(tmp_path)))

    assert len(rows) == 1
    assert rows[0]["status"] == "ready"
    assert rows[0]["match_method"] == "basename"
    assert rows[0]["proposed_name"] == "Show - 01.srt"


def test_one_side_unparseable_still_matches_by_order():
    """회차를 한쪽만 추출할 수 있어도 순서 기반으로 반드시 매칭된다."""
    videos = ["[Grp] Show - 01 [1080p].mkv", "[Grp] Show - 02 [1080p].mkv"]
    subtitles = ["Show - pilot.smi", "Show - finale.smi"]

    rows = build_match_pairs("C:/media", videos, subtitles)

    assert len(rows) == 2
    assert_invariants(rows, videos, subtitles)
    assert_never_zero_match(rows, videos, subtitles)
    assert all(row["match_method"] == "order" for row in rows)
    assert rows[0]["video_name"] == "[Grp] Show - 01 [1080p].mkv"
    assert rows[0]["subtitle_name"] == "Show - finale.smi"
    assert rows[1]["video_name"] == "[Grp] Show - 02 [1080p].mkv"
    assert rows[1]["subtitle_name"] == "Show - pilot.smi"


def test_mixed_extraction_falls_back_per_file():
    """일부만 회차가 추출되는 폴더에서도 나머지는 순서 기반으로 이어진다."""
    videos = ["Show - 01.mkv", "Show - 02.mkv", "Show - 03.mkv"]
    subtitles = ["Show - 01Sub.smi", "Show - extra.smi", "Show - 03Sub.smi"]

    rows = build_match_pairs("C:/media", videos, subtitles)

    assert len(rows) == 3
    assert_invariants(rows, videos, subtitles)
    assert_never_zero_match(rows, videos, subtitles)
    assert sum(row["match_method"] == "episode" for row in rows) == 2
    assert sum(row["match_method"] == "order" for row in rows) == 1


# ---------------------------------------------------------------------------
# 경계 상황
# ---------------------------------------------------------------------------

def test_duplicate_episode_subtitles_do_not_collide():
    """같은 회차 자막이 여러 개여도 파일이 중복 사용되거나 유실되지 않는다."""
    videos = ["Show - 01.mkv"]
    subtitles = ["Show - 01.ko.srt", "Show - 01.en.srt"]

    rows = build_match_pairs("C:/media", videos, subtitles)

    assert len(rows) == 2
    assert_invariants(rows, videos, subtitles)
    assert_never_zero_match(rows, videos, subtitles)
    assert sum(row["status"] == "unmatched" for row in rows) == 1


def test_subtitles_only_folder(tmp_path):
    subtitles = ["Show - 01.smi", "Show - 02.smi"]
    create_files(tmp_path, subtitles)

    rows = flatten(scan_media_folder(str(tmp_path)))

    assert len(rows) == 2
    assert {row["status"] for row in rows} == {"unmatched"}


def test_empty_folder_returns_no_groups(tmp_path):
    assert scan_media_folder(str(tmp_path)) == []


def test_invalid_path_returns_empty_list():
    assert scan_media_folder("Z:/definitely/not/a/real/path") == []


@pytest.mark.parametrize(
    "videos, subtitles",
    [
        # 실제 사고 케이스
        (
            ["[Erai-raws] Show - 01 [720p][HASH].mkv", "[Erai-raws] Show - 02 [720p][HASH].mkv"],
            ["Show - 01Erai.smi", "Show - 02Erai.smi"],
        ),
        # 회차 표기가 전혀 없는 파일
        (["a.mkv", "b.mkv"], ["x.smi", "y.smi"]),
        # 한쪽만 회차 표기
        (["Show - 01.mkv", "Show - 02.mkv"], ["first.smi", "second.smi"]),
        # 개수 불일치
        (["Show - 01.mkv", "Show - 02.mkv", "Show - 03.mkv"], ["Show - 01.smi"]),
        # 중복 회차
        (["Show - 01.mkv", "Show - 01 (2).mkv"], ["Show - 01.ko.srt", "Show - 01.en.srt"]),
    ],
)
def test_invariants_hold_and_never_zero_match(videos, subtitles):
    rows = build_match_pairs("C:/media", videos, subtitles)

    assert_invariants(rows, videos, subtitles)
    assert_never_zero_match(rows, videos, subtitles)
    # id는 정렬된 결과 기준으로 0..n-1 이어야 한다
    assert [row["id"] for row in rows] == list(range(len(rows)))
