"""
자막 파일명 자동매칭 회귀 테스트

핵심 원칙
---------
1) 동영상/자막 양쪽에서 회차를 "유일하게" 추출했을 때만 회차 기반 매칭을 사용한다.
2) 순서 기반 매칭은 최후의 수단이며, 양쪽 회차가 명확한데 서로 다르면 연결하지 않는다.
   (예: E01/E02 동영상만 있는데 7.5화 특별편 자막만 있는 폴더)
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
    group_subtitle_bundles,
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
    """자막은 정확히 한 번씩, 동영상은 최소 한 번씩 등장해야 한다."""
    used_videos = [os.path.basename(row["video_path"]) for row in rows if row["video_path"]]
    used_subtitles = [os.path.basename(row["subtitle_path"]) for row in rows if row["subtitle_path"]]

    assert len(used_subtitles) == len(set(used_subtitles)), "자막이 중복 매칭되었습니다"
    assert sorted(subtitles) == sorted(used_subtitles), "자막 누락/추가 발생"
    assert set(used_videos) == set(videos), "동영상 누락/추가 발생"


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


def test_language_suffix_subtitle_is_preserved(tmp_path):
    """언어 코드가 붙은 자막은 언어 코드를 유지한 채 동영상 이름에 맞춘다."""
    videos = ["Show - 01.mkv"]
    subtitles = ["Other - 01.ko.srt"]
    create_files(tmp_path, videos + subtitles)

    rows = flatten(scan_media_folder(str(tmp_path)))

    assert len(rows) == 1
    assert rows[0]["match_method"] == "episode"
    assert rows[0]["proposed_name"] == "Show - 01.ko.srt"
    assert rows[0]["status"] == "ready"


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

def test_duplicate_episode_subtitles_all_attach_to_video():
    """같은 회차 자막이 여러 개(다국어)여도 모두 하나의 동영상에 연결된다."""
    videos = ["Show - 01.mkv"]
    subtitles = ["Show - 01.ko.srt", "Show - 01.en.srt"]

    rows = build_match_pairs("C:/media", videos, subtitles)

    assert len(rows) == 2
    assert_invariants(rows, videos, subtitles)
    assert_never_zero_match(rows, videos, subtitles)
    assert [row["video_name"] for row in rows] == ["Show - 01.mkv", "Show - 01.mkv"]
    # 언어 코드가 유지되어 서로 덮어쓰지 않는다
    assert sorted(row["proposed_name"] for row in rows) == ["Show - 01.en.srt", "Show - 01.ko.srt"]
    assert {row["status"] for row in rows} == {"synced"}


def test_multiple_subtitle_formats_attach_to_same_video(tmp_path):
    """실제 사고 폴더 형태: mkv 13개 + smi 13개 + ko.srt 13개 -> 26쌍 전부 매칭."""
    videos = [
        f"[Erai-raws] Kaoru Hana wa Rin to Saku - {n:02d} "
        f"[720p NF WEB-DL AVC AAC][MultiSub][{n:08X}].mkv"
        for n in range(1, 14)
    ]
    subtitles = (
        [f"Kaoru Hana wa Rin to Saku - {n:02d}Erai.smi" for n in range(1, 14)]
        + [f"Kaoru Hana wa Rin to Saku - {n:02d}Erai.ko.srt" for n in range(1, 14)]
    )
    create_files(tmp_path, videos + subtitles)

    rows = flatten(scan_media_folder(str(tmp_path)))

    assert len(rows) == 26
    assert sum(row["status"] == "ready" for row in rows) == 26
    assert_never_zero_match(rows, videos, subtitles)
    assert_invariants(rows, videos, subtitles)

    # 동영상마다 자막 2개(.smi, .ko.srt)가 정확한 회차로 연결
    per_video = {}
    for row in rows:
        per_video.setdefault(row["video_name"], []).append(row["subtitle_name"])
    assert len(per_video) == 13
    assert all(len(names) == 2 for names in per_video.values())

    for row in rows:
        video_ep = int(re.search(r"- (\d{2}) \[", row["video_name"]).group(1))
        subtitle_ep = int(re.search(r"- (\d{2})Erai", row["subtitle_name"]).group(1))
        assert video_ep == subtitle_ep
        assert row["proposed_name"] in (
            row["video_name"].replace(".mkv", ".smi"),
            row["video_name"].replace(".mkv", ".ko.srt"),
        )


def test_conflicting_proposed_names_are_not_auto_renamed():
    """언어 코드 없이 같은 확장자로 겹치면 한쪽만 조용히 실패하지 않도록 충돌 표시."""
    videos = ["Show - 01.mkv"]
    subtitles = ["Show - 01.srt", "Show - 01 (2).srt"]

    rows = build_match_pairs("C:/media", videos, subtitles)

    assert_invariants(rows, videos, subtitles)
    assert {row["status"] for row in rows} == {"synced", "conflict"}
    conflict_rows = [row for row in rows if row["status"] == "conflict"]
    assert len(conflict_rows) == 1
    assert conflict_rows[0]["proposed_path"] == ""
    assert all(row["status"] != "ready" for row in rows)


def test_order_matching_does_not_pair_different_episodes(tmp_path):
    """S00E01/E02 동영상만 있는 폴더의 7.5화 특별편 자막은 순서로 붙이지 않는다."""
    videos = [
        "[Sav1or] So Ra No Wo To (Sound of the Sky) - S00E01 - Drinking Party Fortress Battle [1080p].mkv",
        "[Sav1or] So Ra No Wo To (Sound of the Sky) - S00E02 - The Sound of the Sky [1080p].mkv",
    ]
    subtitles = [
        "OVA Sora no Woto 07.5 (BDRip 1080p AV1 cq38 AAC).ko.srt",
        "OVA Sora no Woto 07.5 (BDRip 1080p AV1 cq38 AAC).smi",
    ]
    create_files(tmp_path, videos + subtitles)

    rows = flatten(scan_media_folder(str(tmp_path)))

    assert_invariants(rows, videos, subtitles)
    # 잘못된 이름으로 바뀌지 않도록 동영상/자막을 하나도 연결하지 않는다
    assert not [row for row in rows if row["video_path"] and row["subtitle_path"]]
    assert not [row for row in rows if row["proposed_name"]]

    unmatched_videos = [row["video_name"] for row in rows if row["video_path"]]
    orphan_subtitles = [row["subtitle_name"] for row in rows if row["subtitle_path"]]
    assert sorted(unmatched_videos) == sorted(videos)
    assert sorted(orphan_subtitles) == sorted(subtitles)
    assert {row["status"] for row in rows} == {"unmatched"}


def test_conflicting_episode_is_skipped_while_others_still_match():
    """일부만 회차가 어긋날 때는 그 항목만 미매칭으로 남기고 나머지는 매칭한다."""
    videos = ["Show - 01.mkv", "Show - 02.mkv", "Show - 03.mkv"]
    subtitles = ["Show - 01.smi", "Show - 02.smi", "Show - 07.5.smi"]

    rows = build_match_pairs("C:/media", videos, subtitles)

    assert_invariants(rows, videos, subtitles)
    matched = [row for row in rows if row["video_path"] and row["subtitle_path"]]
    assert len(matched) == 2
    assert {row["subtitle_name"] for row in matched} == {"Show - 01.smi", "Show - 02.smi"}

    # 03화 동영상과 7.5화 자막은 각각 미매칭으로 남는다
    leftover_videos = [row["video_name"] for row in rows if row["video_path"] and not row["subtitle_path"]]
    orphan_subtitles = [row["subtitle_name"] for row in rows if row["subtitle_path"] and not row["video_path"]]
    assert leftover_videos == ["Show - 03.mkv"]
    assert orphan_subtitles == ["Show - 07.5.smi"]


def test_group_subtitle_bundles_groups_same_stem():
    """확장자/언어 코드만 다른 자막은 순서 매칭 전에 한 묶음으로 묶인다."""
    bundles = group_subtitle_bundles([
        "Show - 01.smi",
        "Show - 01.ko.srt",
        "Show - 02.smi",
    ])

    assert [sorted(bundle) for bundle in bundles] == [
        ["Show - 01.ko.srt", "Show - 01.smi"],
        ["Show - 02.smi"],
    ]


def test_same_stem_subtitles_are_bundled_into_one_video():
    """확장자/언어 코드만 다른 자막(.smi + .ko.srt)은 같은 동영상에 묶여야 한다."""
    videos = ["Show - A.mkv", "Show - B.mkv"]
    subtitles = ["Show - C.smi", "Show - C.ko.srt"]

    rows = build_match_pairs("C:/media", videos, subtitles)

    assert_invariants(rows, videos, subtitles)
    matched = [row for row in rows if row["video_path"] and row["subtitle_path"]]
    assert len(matched) == 2
    assert {row["video_name"] for row in matched} == {"Show - A.mkv"}
    assert {row["subtitle_name"] for row in matched} == set(subtitles)

    # 남은 동영상은 자막 없이 표시된다
    leftover_videos = [row["video_name"] for row in rows if row["video_path"] and not row["subtitle_path"]]
    assert leftover_videos == ["Show - B.mkv"]
    assert not [row for row in rows if row["subtitle_path"] and not row["video_path"]]


def test_bundle_with_different_episode_is_rejected_together():
    """묶음 자막의 회차가 동영상과 다르면 묶음 전체를 미매칭으로 남긴다."""
    videos = ["Show - 01.mkv"]
    subtitles = ["Show - 07.5.smi", "Show - 07.5.ko.srt"]

    rows = build_match_pairs("C:/media", videos, subtitles)

    assert_invariants(rows, videos, subtitles)
    assert not [row for row in rows if row["video_path"] and row["subtitle_path"]]
    assert {row["subtitle_name"] for row in rows if row["subtitle_path"]} == set(subtitles)
    assert [row["video_name"] for row in rows if row["video_path"] and not row["subtitle_path"]] == ["Show - 01.mkv"]


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
