"""정적 파일 캐시 정책 회귀 테스트.

업데이트 후 브라우저가 예전 app.js/style.css를 계속 사용하는 문제를 막기 위해
index.html이 버전 쿼리(?v=)가 붙은 자산 URL을 참조하는지 확인한다.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app.main import APP_VERSION, serve_index  # noqa: E402


def test_index_references_versioned_assets():
    response = serve_index()
    body = response.body.decode("utf-8")

    assert f"style.css?v={APP_VERSION}" in body
    assert f"app.js?v={APP_VERSION}" in body
    # 버전이 붙지 않은 예전 URL이 남아 있으면 캐시가 갱신되지 않을 수 있다
    assert 'href="style.css"' not in body
    assert 'src="app.js"' not in body


def test_index_is_not_cached():
    response = serve_index()

    assert response.headers["cache-control"] == "no-store"
