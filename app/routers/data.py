import datetime
import asyncio
from fastapi import APIRouter, Query
from ..internal.ayame_query import ayame_query
from ..internal.ayame_update import ayame_update
from ..internal.database import mongodb_query

router = APIRouter(
    prefix="/data",
    tags=["data"],
    responses={404: {"description": "Not found"}},
)


def today():
    JST = datetime.timezone(datetime.timedelta(hours=+9), "JST")
    dt_now = datetime.datetime.now(JST)
    return dt_now.strftime("%Y-%m-%d")


@router.get("/pageid")
async def pageid_match(
    pageid: int | None = Query(19439882),
    date: str | None = Query(None),
):
    """
    pageidに完全一致する対象のデータを返します。

    日付指定なし:
      - 今日の日付でDBにデータがあればそれを返す
      - なければCromから部分更新して即座に返却、バックグラウンドでキュー投入
    日付指定あり:
      - 指定日付のデータを返す（従来通り）
    """
    # 日付指定時は従来の挙動
    if date is not None:
        return await ayame_query.pageid_match(pageid, date)

    # 日付指定なし: 今日の日付でチェック
    today_str = today()
    query_id = mongodb_query.perfect_match("id", pageid)
    query_date = mongodb_query.perfect_match("date", today_str)
    query = mongodb_query.and_query(query_id, query_date)

    # 今日のデータ存在確認
    today_data = await mongodb_query.collection_data.find_one(query, {"_id": 0})

    if today_data is not None:
        # 今日のデータあり → そのまま返却
        return today_data

    # 今日のデータなし → Cromから部分更新して即座に返却
    # 部分更新実行（同期的に待つ）
    updated = await ayame_update.partial_update_from_crom(pageid)

    if not updated:
        # Cromにもデータがない場合
        return {"page_id": pageid, "found": False}

    # バックグラウンドでキュー投入（完全更新用）
    # fire-and-forget: DBに直接投入
    asyncio.create_task(_enqueue_for_full_update(pageid))

    # 更新後のデータを再取得して返却
    updated_data = await mongodb_query.collection_data.find_one(query, {"_id": 0})
    if updated_data:
        updated_data["data_state"] = "partial"
        updated_data["queued_for_full"] = True
        return updated_data

    # 万が一取得失敗
    return {"page_id": pageid, "found": False}


async def _enqueue_for_full_update(page_id: int):
    """バックグラウンドタスク: キューに投入（DBに直接書き込み）"""
    from importlib import import_module

    uq = import_module("app.internal.update_queue")
    await uq.enqueue(page_id, force=True)


@router.get("/date")
async def date(
    pageid: int | None = Query(19439882),
):
    """
    pageidに完全一致する対象のデータを返します。\n
    日付が指定されていない・形式が間違っている場合最新データを返します。\n
    正しく日付が指定されているがデータが存在しない場合、nullを返します。
    """
    _filter = {
        "_id": 0,
        "date": 1,
    }
    result = await ayame_query.all_pageid_data(pageid, _filter)
    result = [doc["date"] for doc in result]
    return result


@router.get("/rating")
async def rating(
    pageid: int | None = Query(19439882),
):
    """
    pageidに完全一致する対象の全区間のratingを返します。\n
    データが存在しない場合、nullを返します。
    """
    _filter = {"_id": 0, "date": 1, "rating": 1}
    result = await ayame_query.all_pageid_data(pageid, _filter)
    return result
