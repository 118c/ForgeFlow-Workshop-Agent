import pytest

from app.core.llm import extract_json_object


def test_extract_json_from_markdown_and_surrounding_text():
    payload = extract_json_object('分析如下：```json\n{"title":"日计划","risks":[]}\n```结束')
    assert payload == {"title": "日计划", "risks": []}


def test_extract_json_rejects_incomplete_output():
    with pytest.raises(ValueError):
        extract_json_object('{"title":"broken"')

