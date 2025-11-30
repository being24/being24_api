from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.internal.update_queue import (
    MIN_REENQUEUE_INTERVAL_SECONDS,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    cleanup_completed,
    enqueue,
    get_pending,
    mark_completed,
    mark_failed,
    mark_processing,
    reset_failed,
)


@pytest.fixture
def mock_db():
    """MongoDB操作のモック"""
    with patch("app.internal.update_queue.mongodb_query") as mock:
        # コレクションメソッドは非同期のためAsyncMockを設定
        collection = MagicMock()
        collection.find_one = AsyncMock()
        collection.insert_one = AsyncMock()
        collection.update_one = AsyncMock()
        collection.delete_many = AsyncMock()
        collection.update_many = AsyncMock()
        # findはチェーン可能なカーソル(MagicMock)を返す
        collection.find = MagicMock()
        mock.collection_update_queue = collection
        yield mock


@pytest.mark.asyncio
async def test_enqueue_new_page(mock_db):
    """新規page_idのenqueueが成功することを確認"""
    mock_db.collection_update_queue.find_one.return_value = None
    mock_db.collection_update_queue.insert_one.return_value = AsyncMock()

    result = await enqueue(12345)

    assert result is True
    mock_db.collection_update_queue.insert_one.assert_called_once()
    call_args = mock_db.collection_update_queue.insert_one.call_args[0][0]
    assert call_args["page_id"] == 12345
    assert call_args["status"] == STATUS_PENDING
    assert call_args["priority"] == 1
    assert call_args["request_count"] == 1


@pytest.mark.asyncio
async def test_enqueue_existing_page_within_interval(mock_db):
    """TTL内の再enqueueがスキップされることを確認"""
    now = datetime.now(timezone.utc)
    existing_doc = {
        "page_id": 12345,
        "last_enqueued_at": now - timedelta(seconds=900),  # 15分前
        "request_count": 1,
    }
    mock_db.collection_update_queue.find_one.return_value = existing_doc

    result = await enqueue(12345, force=False)

    assert result is False
    mock_db.collection_update_queue.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_enqueue_existing_page_force(mock_db):
    """force=Trueで強制enqueueできることを確認"""
    now = datetime.now(timezone.utc)
    existing_doc = {
        "page_id": 12345,
        "last_enqueued_at": now - timedelta(seconds=900),
        "request_count": 2,
    }
    mock_db.collection_update_queue.find_one.return_value = existing_doc
    mock_db.collection_update_queue.update_one.return_value = AsyncMock()

    result = await enqueue(12345, force=True)

    assert result is True
    mock_db.collection_update_queue.update_one.assert_called_once()


@pytest.mark.asyncio
async def test_enqueue_existing_page_ttl_expired(mock_db):
    """TTL経過後の再enqueueが成功することを確認"""
    now = datetime.now(timezone.utc)
    existing_doc = {
        "page_id": 12345,
        "last_enqueued_at": now
        - timedelta(seconds=MIN_REENQUEUE_INTERVAL_SECONDS + 100),
        "request_count": 3,
    }
    mock_db.collection_update_queue.find_one.return_value = existing_doc
    mock_db.collection_update_queue.update_one.return_value = AsyncMock()

    result = await enqueue(12345, force=False)

    assert result is True
    mock_db.collection_update_queue.update_one.assert_called_once()


@pytest.mark.asyncio
async def test_get_pending(mock_db):
    """pending状態のpage_idリスト取得を確認"""
    # findメソッドをAsyncMockでモック
    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.limit = MagicMock(return_value=mock_cursor)

    # async iteratorのモック
    async def async_iter():
        for doc in [{"page_id": 111}, {"page_id": 222}, {"page_id": 333}]:
            yield doc

    mock_cursor.__aiter__ = lambda self: async_iter()
    mock_db.collection_update_queue.find.return_value = mock_cursor

    result = await get_pending(batch_size=10)

    assert result == [111, 222, 333]
    mock_db.collection_update_queue.find.assert_called_once_with(
        {"status": STATUS_PENDING}
    )


@pytest.mark.asyncio
async def test_mark_processing(mock_db):
    """processing状態への更新を確認"""
    mock_db.collection_update_queue.update_one.return_value = AsyncMock()

    await mark_processing(456)

    mock_db.collection_update_queue.update_one.assert_called_once()
    call_args = mock_db.collection_update_queue.update_one.call_args
    assert call_args[0][0] == {"page_id": 456}
    assert call_args[0][1]["$set"]["status"] == STATUS_PROCESSING


@pytest.mark.asyncio
async def test_mark_completed(mock_db):
    """completed状態への更新を確認"""
    mock_db.collection_update_queue.update_one.return_value = AsyncMock()

    await mark_completed(789)

    mock_db.collection_update_queue.update_one.assert_called_once()
    call_args = mock_db.collection_update_queue.update_one.call_args
    assert call_args[0][0] == {"page_id": 789}
    assert call_args[0][1]["$set"]["status"] == STATUS_COMPLETED


@pytest.mark.asyncio
async def test_mark_failed(mock_db):
    """failed状態への更新とretry_count増加を確認"""
    mock_db.collection_update_queue.update_one.return_value = AsyncMock()

    await mark_failed(999, "Test error message")

    mock_db.collection_update_queue.update_one.assert_called_once()
    call_args = mock_db.collection_update_queue.update_one.call_args
    assert call_args[0][0] == {"page_id": 999}
    assert call_args[0][1]["$set"]["status"] == STATUS_FAILED
    assert "Test error" in call_args[0][1]["$set"]["last_error"]
    assert call_args[0][1]["$inc"]["retry_count"] == 1


@pytest.mark.asyncio
async def test_reset_failed(mock_db):
    """retry_count上限未満のfailedをpendingに戻すことを確認"""
    mock_db.collection_update_queue.update_many.return_value = AsyncMock()

    await reset_failed(max_retry=3)

    mock_db.collection_update_queue.update_many.assert_called_once()
    call_args = mock_db.collection_update_queue.update_many.call_args
    assert call_args[0][0]["status"] == STATUS_FAILED
    assert call_args[0][0]["retry_count"]["$lt"] == 3
    assert call_args[0][1]["$set"]["status"] == STATUS_PENDING


@pytest.mark.asyncio
async def test_cleanup_completed(mock_db):
    """古いcompleted状態のレコード削除を確認"""
    mock_result = AsyncMock()
    mock_result.deleted_count = 5
    mock_db.collection_update_queue.delete_many.return_value = mock_result

    await cleanup_completed(ttl_hours=24)

    mock_db.collection_update_queue.delete_many.assert_called_once()
    call_args = mock_db.collection_update_queue.delete_many.call_args
    assert call_args[0][0]["status"] == STATUS_COMPLETED
    assert "$lt" in call_args[0][0]["updated_at"]
