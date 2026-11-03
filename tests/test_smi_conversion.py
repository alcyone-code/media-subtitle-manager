"""SMI ➡️ SRT 변환 회귀 테스트.

기본 출력 형식이 `.ko.srt`인지 확인한다. (기존 `.srt`는 명시적으로 선택 가능해야 한다)
"""

import os

from subtitle_utils import convert_smi_file

SAMPLE_SMI = """<SAMI>
<HEAD>
<TITLE>Sample</TITLE>
</HEAD>
<BODY>
<SYNC Start=1000><P Class=KRCC>첫 번째 자막입니다.
<SYNC Start=3000><P Class=KRCC>&nbsp;
<SYNC Start=4000><P Class=KRCC>두 번째 자막입니다.
<SYNC Start=6000><P Class=KRCC>&nbsp;
</BODY>
</SAMI>
"""


def write_sample(tmp_path, name="Show - 01.smi"):
    path = tmp_path / name
    path.write_text(SAMPLE_SMI, encoding="utf-8")
    return path


def test_default_output_is_ko_srt(tmp_path):
    source = write_sample(tmp_path)

    ok, result_path = convert_smi_file(str(source))

    assert ok, result_path
    assert os.path.basename(result_path) == "Show - 01.ko.srt"
    assert os.path.exists(result_path)
    # 기본값은 원본을 삭제하지 않는다
    assert source.exists()


def test_explicit_srt_output_still_available(tmp_path):
    source = write_sample(tmp_path)

    ok, result_path = convert_smi_file(str(source), output_format="srt")

    assert ok, result_path
    assert os.path.basename(result_path) == "Show - 01.srt"
    assert os.path.exists(result_path)


def test_converted_srt_contains_timestamps(tmp_path):
    source = write_sample(tmp_path)

    ok, result_path = convert_smi_file(str(source))

    assert ok, result_path
    content = open(result_path, encoding="utf-8").read()
    assert "00:00:01,000 --> " in content
    assert "첫 번째 자막입니다." in content
