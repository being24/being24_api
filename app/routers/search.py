import datetime
from fastapi import APIRouter, Query
from ..internal.ayame_query import ayame_query

router = APIRouter(
    prefix="/search",
    tags=["search"],
    responses={404: {"description": "Not found"}},
)


def today(offset_day=0):
    td = datetime.timedelta(days=offset_day)
    JST = datetime.timezone(datetime.timedelta(hours=+9), "JST")
    dt_now = datetime.datetime.now(JST) + td
    return dt_now.strftime("%Y-%m-%d")


def result_filter(docs, pageid):
    if pageid:
        result = [doc["id"] for doc in docs if "id" in doc]
    else:
        # リスト内包表記が長すぎるので普通に表記
        result = []
        for doc in docs:
            if "metatitle" in doc:
                result.append(doc["metatitle"])
            elif "fullname" in doc:
                result.append(doc["fullname"])
    return result


@router.get("/title")
async def title(
    title: str | None = Query(None),
    page: int | None = Query(1),
    show: int | None = Query(25),
    pageid: bool | None = False,
):
    """
    fullnameもしくはmetatitleによる部分一致検索\n
    キーワード入力補助を想定\n
    limitは最大1000\n
    戻り値:fullnameとmetatitle(優先)の複合 もしくは pageid
    """
    page = abs(page)
    show = min(100, abs(show))
    _filter = {"_id": 0, "id": 1, "metatitle": 1, "fullname": 1}
    result = await ayame_query.title_partial_match(
        title,
        page,
        show,
        _filter,
    )
    return result_filter(result, pageid)


@router.get("/tag")
async def tag(
    tags: list[str] | None = Query(None),
    page: int | None = Query(1),
    show: int | None = Query(25),
    pageid: bool | None = False,
):
    """
    タグによる部分一致and検索\n
    limitは最大1000\n
    戻り値:fullnameとmetatitle(優先)の複合 もしくは pageid
    """
    page = abs(page)
    show = min(100, abs(show))
    if tags is None:
        return []
    _filter = {"_id": 0, "id": 1, "metatitle": 1, "fullname": 1}
    result = await ayame_query.tag_partial_match(tags, page, show, _filter)
    return result_filter(result, pageid)


@router.get("/create_at")
async def create_at(
    _from: str | None = Query(today(-30)),
    _to: str | None = Query(today()),
    page: int | None = Query(1),
    show: int | None = Query(25),
    pageid: bool | None = False,
):
    """
    作成日の範囲による検索\n
    limitは最大1000\n
    戻り値:fullnameとmetatitle(優先)の複合 もしくは pageid
    """
    page = abs(page)
    show = min(100, abs(show))
    _filter = {"_id": 0, "id": 1, "metatitle": 1, "fullname": 1}
    result = await ayame_query.create_at_range_match(_from, _to, page, show, _filter)
    return result_filter(result, pageid)


@router.get("/complex")
async def _complex(
    title: str | None = Query(None),
    tags: list[str] | None = Query(None),
    author: str | None = Query(None),
    rate_min: int | None = Query(None),
    rate_max: int | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    page: int | None = Query(1),
    show: int | None = Query(25),
):
    """
    複合検索。おもにページ表示用\n
    検索条件の指定がなければ全件を取得\n
    showは最大100まで\n
    戻り値:fullnameとmetatitle(優先)の複合 もしくは pageid
    """

    _filter = {
        "_id": 0,
        "id": 1,
        "metatitle": 1,
        "fullname": 1,
        "tags": 1,
        "created_by_unix": 1,
        "rating": 1,
        "created_at": 1,
        "date": 1,
    }
    page = abs(page)
    show = min(100, abs(show))
    result = await ayame_query.complex_search(
        title, tags, author, rate_min, rate_max, date_from, date_to, page, show, _filter
    )
    return result
