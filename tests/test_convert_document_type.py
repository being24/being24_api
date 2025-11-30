import datetime
import json
import pathlib

from app.internal.ayame_update import ayame_update


def _load_one_output_line() -> dict:
    p = pathlib.Path("json/output.jsonl")
    assert p.exists(), "json/output.jsonl not found"
    # 1行目を読み取り
    with p.open("r", encoding="utf-8") as f:
        line = f.readline().strip()
    return json.loads(line)


def test_convert_document_type_matches_output_shape():
    src = _load_one_output_line()

    # output.jsonlはISO文字列やlistのタグなど、実データ形で入る
    doc = ayame_update.convert_docment_type(src)

    # 日付はdatetimeへ（nullはNoneのまま）
    assert isinstance(doc["created_at"], datetime.datetime)
    assert isinstance(doc["updated_at"], datetime.datetime)
    # commented_atはNoneの場合もある
    assert (doc["commented_at"] is None) or isinstance(
        doc["commented_at"], datetime.datetime
    )

    # タグは既にlistなら維持される
    assert isinstance(doc["tags"], list)

    # 数値変換
    assert isinstance(doc["rating"], (int, float))
    assert isinstance(doc["revisions"], int)
    assert isinstance(doc["id"], int)


def test_same_dictionary_check_ignores_date_and_id():
    base = {"id": 1, "fullname": "scp-001", "rating": 10, "date": "2025-11-30"}
    changed = {"id": 1, "fullname": "scp-001", "rating": 10, "date": "2025-11-29"}

    assert ayame_update.same_dictionary_check(base, changed) is True
