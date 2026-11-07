"""미리보기 상단 요약(변경 예정 + 미매칭) 회귀 테스트.

"자막 N개 변경 예정" 배지 옆에 미매칭 현황이 함께 보이도록
index.html과 app.js가 연결되어 있는지 확인한다.
(미매칭 = 동영상과 연결되지 않아 자동으로 이름이 바뀌지 않는 자막)
"""

import os
import re

STATIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "backend",
    "app",
    "static",
)


def read_static(name):
    with open(os.path.join(STATIC_DIR, name), encoding="utf-8") as f:
        return f.read()


def test_index_has_unmatched_badge_next_to_preview_count():
    html = read_static("index.html")
    summary = re.search(r'<div class="preview-summary".*?</div>', html, re.S)

    assert summary, "미리보기 상단 요약 영역이 없습니다"
    block = summary.group(0)
    assert 'id="txt-preview-count"' in block, "변경 예정 배지가 요약 영역에 없습니다"
    assert 'id="txt-unmatched-count"' in block, "미매칭 배지가 요약 영역에 없습니다"


def test_app_updates_unmatched_badge():
    js = read_static("app.js")

    assert "getElementById('txt-unmatched-count')" in js
    assert "updateUnmatchedBadge(" in js
