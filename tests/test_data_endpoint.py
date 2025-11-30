from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@pytest.fixture
def mock_db():
    """MongoDB操作のモック"""
    with patch("app.routers.data.mongodb_query") as mock:
        mock.collection_data = AsyncMock()
        yield mock


@pytest.fixture
def mock_partial_update():
    """partial_update_from_crom関数のモック"""
    with patch("app.routers.data.ayame_update.partial_update_from_crom") as mock:
        yield mock


@pytest.fixture
def mock_enqueue():
    """update_queue.enqueue関数のモック"""
    with patch("app.routers.data.import_module") as mock_import:
        mock_queue = AsyncMock()
        mock_queue.enqueue = AsyncMock()
        mock_import.return_value = mock_queue
        yield mock_queue.enqueue


@pytest.mark.asyncio
async def test_pageid_endpoint_with_today_data(mock_db):
    """今日のデータが存在する場合、既存データを返すことを確認"""
    mock_db.collection_data.find_one.return_value = {
        "page_id": 12345,
        "rating": 100,
        "date": "2024-01-15",
        "tags": ["scp"],
    }

    response = client.get("/data/pageid?pageid=12345")

    assert response.status_code == 200
    data = response.json()
    assert data["page_id"] == 12345
    assert data["rating"] == 100
    assert "data_state" not in data  # 既存データはフラグなし


@pytest.mark.asyncio
async def test_pageid_endpoint_missing_calls_crom(mock_db, mock_partial_update):
    """今日のデータがない場合、Cromから取得することを確認"""
    # 最初のfind_one: 今日のデータなし
    # 2回目のfind_one: 更新後のデータ取得
    mock_db.collection_data.find_one.side_effect = [
        None,
        {
            "page_id": 99999,
            "rating": 50,
            "date": "2024-01-15",
            "tags": ["tale"],
        },
    ]
    mock_partial_update.return_value = True

    response = client.get("/data/pageid?pageid=99999")

    assert response.status_code == 200
    data = response.json()
    assert data["page_id"] == 99999
    assert data["data_state"] == "partial"
    assert data["queued_for_full"] is True
    mock_partial_update.assert_called_once_with(99999)


@pytest.mark.asyncio
async def test_pageid_endpoint_crom_not_found(mock_db, mock_partial_update):
    """Cromにもデータがない場合、found=Falseを返すことを確認"""
    mock_db.collection_data.find_one.return_value = None
    mock_partial_update.return_value = False

    response = client.get("/data/pageid?pageid=77777")

    assert response.status_code == 200
    data = response.json()
    assert data["page_id"] == 77777
    assert data["found"] is False


@pytest.mark.asyncio
async def test_pageid_endpoint_with_date_param(mock_db):
    """日付指定時は従来の挙動（ayame_query使用）を確認"""
    with patch("app.routers.data.ayame_query.pageid_match") as mock_query:
        mock_query.return_value = {"page_id": 12345, "date": "2023-12-01"}

        response = client.get("/data/pageid?pageid=12345&date=2023-12-01")

        assert response.status_code == 200
        mock_query.assert_called_once_with(12345, "2023-12-01")


def test_date_endpoint():
    """日付リストのエンドポイント正常動作を確認"""
    with patch("app.routers.data.ayame_query.all_pageid_data") as mock_all:
        mock_all.return_value = [
            {"date": "2024-01-01"},
            {"date": "2024-01-02"},
            {"date": "2024-01-03"},
        ]

        response = client.get("/data/date?pageid=12345")

        assert response.status_code == 200
        dates = response.json()
        assert dates == ["2024-01-01", "2024-01-02", "2024-01-03"]


def test_rating_endpoint():
    """ratingリストのエンドポイント正常動作を確認"""
    with patch("app.routers.data.ayame_query.all_pageid_data") as mock_all:
        mock_all.return_value = [
            {"date": "2024-01-01", "rating": 10},
            {"date": "2024-01-02", "rating": 20},
        ]

        response = client.get("/data/rating?pageid=12345")

        assert response.status_code == 200
        ratings = response.json()
        assert len(ratings) == 2
        assert ratings[0]["rating"] == 10
