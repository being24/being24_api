import datetime
from fastapi import APIRouter, Query
from ..internal.ayame_query import ayame_query

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
    pageid: int | None = Query(19439882), date: str | None = Query(None)
):
    """
    pageidに完全一致する対象のデータを返します。\n
    日付が指定されていない・形式が間違っている場合最新データを返します。\n
    正しく日付が指定されているがデータが存在しない場合、nullを返します。
    """
    return await ayame_query.pageid_match(pageid, date)


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
