import datetime
from typing import List

from .database import mongodb_query
from .logger import logger

# キュー内 status 定義
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

MIN_REENQUEUE_INTERVAL_SECONDS = 1800  # 30分


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _priority_from_request_count(count: int) -> int:
    # シンプルな優先度: 回数そのまま
    return count


async def enqueue(page_id: int, force: bool = False) -> bool:
    """page_idを更新キューへ投入 (存在すれば更新)。

    再投入条件:
      - force=True
      - 前回投入から MIN_REENQUEUE_INTERVAL_SECONDS 経過
    """
    now = _utc_now()
    query = {"page_id": page_id}
    existing = await mongodb_query.collection_update_queue.find_one(query)
    if existing is None:
        doc = {
            "page_id": page_id,
            "requested_at": now,
            "last_requested_at": now,
            "request_count": 1,
            "status": STATUS_PENDING,
            "priority": 1,
            "retry_count": 0,
            "last_error": None,
            "updated_at": now,
            "last_enqueued_at": now,
        }
        await mongodb_query.collection_update_queue.insert_one(doc)
        logger.info(f"enqueue new page_id={page_id}")
        return True

    # 既存レコード更新可否判定
    last_enqueued_at: datetime.datetime = existing.get("last_enqueued_at")
    if not force and last_enqueued_at:
        delta = (now - last_enqueued_at).total_seconds()
        if delta < MIN_REENQUEUE_INTERVAL_SECONDS:
            logger.debug(
                f"skip enqueue page_id={page_id} delta={delta:.1f}s (<{MIN_REENQUEUE_INTERVAL_SECONDS}s)"
            )
            return False

    # 更新
    new_count = int(existing.get("request_count", 0)) + 1
    update = {
        "$set": {
            "last_requested_at": now,
            "status": STATUS_PENDING,
            "priority": _priority_from_request_count(new_count),
            "updated_at": now,
            "last_enqueued_at": now,
        },
        "$inc": {"request_count": 1},
    }
    await mongodb_query.collection_update_queue.update_one(query, update)
    logger.info(f"re-enqueue page_id={page_id} count={new_count}")
    return True


async def get_pending(batch_size: int = 20) -> List[int]:
    """pending状態のpage_idを優先度順に取得"""
    cursor = (
        mongodb_query.collection_update_queue.find({"status": STATUS_PENDING})
        .sort([("priority", -1), ("requested_at", 1)])
        .limit(batch_size)
    )
    ids: List[int] = []
    async for doc in cursor:
        ids.append(int(doc["page_id"]))
    return ids


async def mark_processing(page_id: int):
    now = _utc_now()
    await mongodb_query.collection_update_queue.update_one(
        {"page_id": page_id},
        {"$set": {"status": STATUS_PROCESSING, "updated_at": now}},
    )


async def mark_completed(page_id: int):
    now = _utc_now()
    await mongodb_query.collection_update_queue.update_one(
        {"page_id": page_id},
        {"$set": {"status": STATUS_COMPLETED, "updated_at": now}},
    )


async def mark_failed(page_id: int, error_message: str):
    now = _utc_now()
    await mongodb_query.collection_update_queue.update_one(
        {"page_id": page_id},
        {
            "$set": {
                "status": STATUS_FAILED,
                "updated_at": now,
                "last_error": error_message[:500],
            },
            "$inc": {"retry_count": 1},
        },
    )
    logger.warning(f"page_id={page_id} failed: {error_message}")


async def reset_failed(max_retry: int = 3):
    """一定回数未満のFAILEDを再度PENDINGへ戻す"""
    now = _utc_now()
    query = {"status": STATUS_FAILED, "retry_count": {"$lt": max_retry}}
    update = {"$set": {"status": STATUS_PENDING, "updated_at": now}}
    await mongodb_query.collection_update_queue.update_many(query, update)


async def cleanup_completed(ttl_hours: int = 24):
    """完了済みで一定時間経過したものを削除 (任意)"""
    threshold = _utc_now() - datetime.timedelta(hours=ttl_hours)
    query = {"status": STATUS_COMPLETED, "updated_at": {"$lt": threshold}}
    result = await mongodb_query.collection_update_queue.delete_many(query)
    if result.deleted_count:
        logger.info(f"cleanup completed removed={result.deleted_count}")
