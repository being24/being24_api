from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.internal.ayame_update import ayame_update


@pytest.fixture
def mock_crom_data():
    """Crom APIからのレスポンスモック"""
    return [
        SimpleNamespace(
            id=1445429602,
            rating=18,
            date="2025-11-30",
            tags=["jp", "ハブ", "メタデータ", "合作", "合同編集"],
            metatitle="SCP-JP一覧（3000-JP～3999-JP）",
            fullname="scp-series-jp-4",
            title="SCP-JP一覧（3000-JP～3999-JP）",
        )
    ]


@pytest.fixture
def mock_get_date_pages():
    """get_date_pages_by_id関数のモック"""
    with patch(
        "app.internal.ayame_update.get_date_pages_by_id", new_callable=AsyncMock
    ) as mock:
        yield mock


@pytest.fixture
def mock_db():
    """MongoDB操作のモック"""
    with patch("app.internal.ayame_update.mongodb_query") as mock:
        # 非同期メソッドを設定
        data = MagicMock()
        data.find_one = AsyncMock()
        data.insert_one = AsyncMock()
        data.update_one = AsyncMock()
        mock.collection_data = data

        search = MagicMock()
        search.find_one = AsyncMock()
        search.insert_one = AsyncMock()
        search.update_one = AsyncMock()
        mock.collection_search = search
        yield mock


@pytest.fixture
def mock_update_queue():
    """update_queueモジュールのモック"""
    mock_queue = MagicMock()
    mock_queue.get_pending = AsyncMock()
    mock_queue.mark_processing = AsyncMock()
    mock_queue.mark_completed = AsyncMock()
    mock_queue.mark_failed = AsyncMock()

    with patch.dict("sys.modules", {"app.internal.update_queue": mock_queue}):
        yield mock_queue


@pytest.mark.asyncio
async def test_partial_update_from_crom_success(
    mock_get_date_pages, mock_db, mock_crom_data
):
    """Cromからのデータで部分更新が成功することを確認"""
    mock_get_date_pages.return_value = mock_crom_data
    # 既存データなしとしてinsertの経路に入る
    mock_db.collection_data.find_one.return_value = None
    mock_db.collection_data.insert_one.return_value = AsyncMock()

    result = await ayame_update.partial_update_from_crom(1445429602)

    assert result is True
    mock_get_date_pages.assert_called_once_with(1445429602)
    mock_db.collection_data.insert_one.assert_called()
    # 検索用コレクションへの反映
    assert (
        mock_db.collection_search.insert_one.called
        or mock_db.collection_search.update_one.called
    )

    # 実際に呼ばれた update_one の引数から $set を取得
    if mock_db.collection_data.update_one.called:
        call = mock_db.collection_data.update_one.call_args
    elif mock_db.collection_search.update_one.called:
        call = mock_db.collection_search.update_one.call_args
    else:
        pytest.fail("No update_one call captured")

    set_data = call[0][1]["$set"]
    assert set_data["rating"] == 18
    assert set_data["date"] == "2025-11-30"
    assert set_data["tags"] == ["jp", "ハブ", "メタデータ", "合作", "合同編集"]
    assert set_data["metatitle"] == "SCP-JP一覧（3000-JP～3999-JP）"


@pytest.mark.asyncio
async def test_partial_update_from_crom_page_not_found(mock_get_date_pages, mock_db):
    """Cromにpage_idが存在しない場合の処理を確認"""
    mock_get_date_pages.return_value = []

    result = await ayame_update.partial_update_from_crom(99999)

    assert result is False
    mock_db.collection_data.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_partial_update_from_crom_api_error(mock_get_date_pages, mock_db):
    """Crom API呼び出しエラー時の処理を確認"""
    mock_get_date_pages.side_effect = Exception("Crom API error")

    result = await ayame_update.partial_update_from_crom(12345)

    assert result is False


@pytest.mark.asyncio
async def test_process_partial_queue_success(
    mock_update_queue, mock_get_date_pages, mock_db, mock_crom_data
):
    """キュー処理が正常に動作することを確認"""
    mock_update_queue.get_pending.return_value = [1445429602, 67890]
    # 両方とも正常データを返す
    mock_get_date_pages.side_effect = [mock_crom_data, mock_crom_data]
    mock_db.collection_data.find_one.return_value = None
    mock_db.collection_data.insert_one.return_value = AsyncMock()
    mock_db.collection_search.find_one.return_value = None
    mock_db.collection_search.insert_one.return_value = AsyncMock()

    await ayame_update.process_partial_queue(batch_size=10)

    assert mock_update_queue.mark_processing.call_count == 2
    assert mock_update_queue.mark_completed.call_count == 2
    assert mock_update_queue.mark_failed.call_count == 0


@pytest.mark.asyncio
async def test_process_partial_queue_with_failure(
    mock_update_queue, mock_get_date_pages, mock_db
):
    """キュー処理中のエラーがfailedとしてマークされることを確認"""
    mock_update_queue.get_pending.return_value = [11111, 22222]
    mock_get_date_pages.side_effect = [
        Exception("Crom connection timeout"),
        [],  # page_id 22222 は存在しない
    ]

    await ayame_update.process_partial_queue(batch_size=10)

    assert mock_update_queue.mark_processing.call_count == 2
    assert mock_update_queue.mark_completed.call_count == 0
    assert mock_update_queue.mark_failed.call_count == 2


@pytest.mark.asyncio
async def test_process_partial_queue_empty(mock_update_queue):
    """キューが空の場合に正常終了することを確認"""
    mock_update_queue.get_pending.return_value = []

    await ayame_update.process_partial_queue(batch_size=10)

    mock_update_queue.get_pending.assert_called_once_with(batch_size=10)
    mock_update_queue.mark_processing.assert_not_called()
