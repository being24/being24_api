import asyncio
import pathlib
import sys
import time
from datetime import datetime, timezone

from gql import Client as GQLClient
from gql import gql
from gql.transport.requests import RequestsHTTPTransport
from wikidot import Client
from wikidot.module.page import PageCollection

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.data_update.models import AyameDatePage, CromPage, PageInfo  # noqa: E402
from app.internal.logger import logger  # noqa: E402


class RecentlyEdited:
    def __init__(self):
        pass

    def get_recently_edited(self, limit: int = 120, hours: int = 12) -> PageCollection:
        with Client() as client:
            site = client.site.get("scp-jp")

            recently_edited = site.pages.search(
                order="updated_at desc",
                limit=limit,
                updated_at=f"last {hours} hours",
            )

        return recently_edited


class CromAPIClient:
    def __init__(self):
        self.endpoint = "https://apiv1.crom.avn.sh/graphql"
        self.transport = RequestsHTTPTransport(url=self.endpoint)

    def get_page_by_wikidot_id(self, wikidot_id: int) -> CromPage | None:
        """Wikidot IDからページ情報を取得"""

        query = gql(
            """
            query Search($wikidot_id: Int!) {
              pageByWikidotId(wikidotId: $wikidot_id) {
                url
                alternateTitles { title }
                attributions { type user { name } }
                wikidotInfo {
                  title
                  tags
                  rating
                  coarseVoteRecords { timestamp direction }
                }
              }
            }
            """
        )

        variables = {"wikidot_id": wikidot_id}

        with GQLClient(
            transport=self.transport, fetch_schema_from_transport=True
        ) as client:
            result = client.execute(query, variable_values=variables)

        data = result.get("pageByWikidotId")
        if data is None:
            return None

        return CromPage.model_validate(data)


class RatingHistoryProcessor:
    """Rating履歴を処理し、日付ごとのAyameDatePageリストを生成するクラス"""

    def generate_date_pages(
        self, page_data: PageInfo, article_id: int, crom_page: CromPage
    ) -> list[AyameDatePage]:
        """
        投票記録から日付ごとのrating履歴を計算し、AyameDatePageのリストを生成

        Args:
            page_data: Wikidotから取得したページ情報
            article_id: ページのWikidot ID
            crom_page: Crom APIから取得したページ情報

        Returns:
            日付ごとのAyameDatePageのリスト
        """
        # ratingの一致確認
        if crom_page.wikidotInfo.rating != page_data.rating:
            logger.warning(
                f"Rating mismatch! Wikidot: {page_data.rating}, Crom: {crom_page.wikidotInfo.rating}, Page: {page_data.fullname}"
            )

        # 日付ごとの最終rating値を計算
        daily_ratings: dict[str, int | float] = {}
        current_rating = page_data.rating

        # 現在のratingから逆算して初期ratingを求める
        initial_rating = current_rating
        for vote in crom_page.wikidotInfo.coarseVoteRecords:
            initial_rating -= vote.direction

        # 各投票を順に適用して日付ごとのratingを記録（API側の順番を信頼）
        rating_at_time = initial_rating
        for vote in crom_page.wikidotInfo.coarseVoteRecords:
            rating_at_time += vote.direction
            date_str = vote.timestamp.strftime("%Y-%m-%d")
            # 同じ日付の場合は上書き（最後の値を保持）
            daily_ratings[date_str] = rating_at_time

        # 最後のratingと現在のratingが一致しない場合は警告を出す
        if rating_at_time != current_rating:
            logger.warning(
                f"Final computed rating {rating_at_time} does not match current rating {current_rating} for page {page_data.fullname}"
            )

        # 日付ごとのAyameDatePageモデルリストを作成
        date_pages: list[AyameDatePage] = []
        for date_str, rating in daily_ratings.items():
            date_page_item = AyameDatePage.create_date_page(
                page_data=page_data,
                metatitle=crom_page.wikidotInfo.title,
                rating=rating,
                article_id=article_id,
                date=date_str,
            )
            date_pages.append(date_page_item)

        # もし日付が一つも生成されなかった場合、現在の日付で1件作成
        if len(date_pages) == 0:
            date_page_item = AyameDatePage.create_date_page(
                page_data=page_data,
                metatitle=crom_page.wikidotInfo.title,
                rating=current_rating,
                article_id=article_id,
                date=page_data.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d"),
            )
            date_pages.append(date_page_item)

        return date_pages

    def generate_date_pages_from_crom_only(
        self, article_id: int, crom_page: CromPage
    ) -> list[AyameDatePage]:
        """
        Crom APIのデータのみから日付ごとのrating履歴を計算し、AyameDatePageのリストを生成

        Wikidotから取得する情報(created_at, updated_at等)は含まれないため、
        デフォルト値またはNoneを使用する。

        Args:
            article_id: ページのWikidot ID
            crom_page: Crom APIから取得したページ情報

        Returns:
            日付ごとのAyameDatePageのリスト
        """
        # 日付ごとの最終rating値を計算
        daily_ratings: dict[str, int | float] = {}
        current_rating = crom_page.wikidotInfo.rating

        # 現在のratingから逆算して初期ratingを求める
        initial_rating = current_rating
        for vote in crom_page.wikidotInfo.coarseVoteRecords:
            initial_rating -= vote.direction

        # 各投票を順に適用して日付ごとのratingを記録（API側の順番を信頼）
        rating_at_time = initial_rating
        for vote in crom_page.wikidotInfo.coarseVoteRecords:
            rating_at_time += vote.direction
            date_str = vote.timestamp.strftime("%Y-%m-%d")
            # 同じ日付の場合は上書き（最後の値を保持）
            daily_ratings[date_str] = rating_at_time

        # 最後のratingと現在のratingが一致しない場合は警告を出す
        if rating_at_time != current_rating:
            logger.warning(
                f"Final computed rating {rating_at_time} does not match current rating {current_rating} for page_id {article_id}"
            )

        # URLからfullnameを抽出（例: https://scp-jp.wikidot.com/scp-XXX -> scp-XXX）
        fullname = (
            crom_page.url.split("/")[-1] if crom_page.url else f"unknown-{article_id}"
        )

        # 日付ごとのAyameDatePageモデルリストを作成
        date_pages: list[AyameDatePage] = []
        for date_str, rating in daily_ratings.items():
            date_page_item = AyameDatePage(
                fullname=fullname,
                title=crom_page.wikidotInfo.title,
                created_at=datetime.now(
                    timezone.utc
                ),  # Crom APIに含まれないためダミー値
                created_by_unix=None,
                created_by_id=None,
                created_by=None,
                updated_at=None,
                updated_by=None,
                updated_by_unix=None,
                updated_by_id=None,
                commented_at=None,
                commented_by=None,
                commented_by_unix=None,
                commented_by_id=None,
                parent_fullname=None,
                comments=0,  # Crom APIに含まれない
                size=0,  # Crom APIに含まれない
                rating=rating,
                rating_votes=0,  # Crom APIに含まれない
                revisions=0,  # Crom APIに含まれない
                tags=crom_page.wikidotInfo.tags,
                metatitle=crom_page.wikidotInfo.title,
                id=article_id,
                date=date_str,
            )
            date_pages.append(date_page_item)

        # もし日付が一つも生成されなかった場合、現在の日付で1件作成
        if len(date_pages) == 0:
            date_page_item = AyameDatePage(
                fullname=fullname,
                title=crom_page.wikidotInfo.title,
                created_at=datetime.now(timezone.utc),
                created_by_unix=None,
                created_by_id=None,
                created_by=None,
                updated_at=None,
                updated_by=None,
                updated_by_unix=None,
                updated_by_id=None,
                commented_at=None,
                commented_by=None,
                commented_by_unix=None,
                commented_by_id=None,
                parent_fullname=None,
                comments=0,
                size=0,
                rating=current_rating,
                rating_votes=0,
                revisions=0,
                tags=crom_page.wikidotInfo.tags,
                metatitle=crom_page.wikidotInfo.title,
                id=article_id,
                date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            )
            date_pages.append(date_page_item)

        return date_pages


def _get_updated_data_sync(
    limit: int = 120, hours: int = 4
) -> dict[int, tuple[list[AyameDatePage], PageInfo]]:
    """
    最近編集（updated_at）のページを取得し、Cromの投票履歴から
    日付ごとの`AyameDatePage`のリストを生成して返す。（同期版）

    Returns:
        dict[page_id, (date_pages, page_info)]
    """
    re = RecentlyEdited()
    crom_client = CromAPIClient()
    processor = RatingHistoryProcessor()

    recently_edited = re.get_recently_edited(limit=limit, hours=hours)

    all_data: dict[int, tuple[list[AyameDatePage], PageInfo]] = {}

    for page in recently_edited:
        page_id = page.id

        page_data = PageInfo.from_wikidot_py(page)
        result = crom_client.get_page_by_wikidot_id(page_id)

        if result is None:
            # logger.info(f"No Crom API data found for page id={page_id}")
            continue

        if result.wikidotInfo.rating != page_data.rating:
            logger.warning(
                f"Rating mismatch! Wikidot: {page_data.rating}, Crom: {result.wikidotInfo.rating}, Page: {page_data.fullname}"
            )
            # この場合は履歴の信頼性が下がるためスキップ
            continue

        # Rating履歴を処理して日付ごとのページリストを生成
        date_pages = processor.generate_date_pages(page_data, page_id, result)

        # logger.info(
        #     f"Generated {len(date_pages)} date records for {page_data.fullname}"
        # )

        if len(date_pages) == 0:
            logger.error(
                f"No date pages generated for {page_data.fullname}, ID: {page_id}"
            )
            continue

        all_data[page_id] = (date_pages, page_data)

    return all_data


async def get_updated_data(
    limit: int = 120, hours: int = 4
) -> dict[int, tuple[list[AyameDatePage], PageInfo]]:
    """
    最近編集（updated_at）のページを取得し、Cromの投票履歴から
    日付ごとの`AyameDatePage`のリストを生成して返す。（非同期版）

    Returns:
        dict[page_id, (date_pages, page_info)]
    """
    return await asyncio.to_thread(_get_updated_data_sync, limit=limit, hours=hours)


def _get_date_pages_by_id_sync(page_id: int) -> list[AyameDatePage]:
    """
    指定されたWikidot IDのページについて、Crom APIのみを使用して
    日付ごとの`AyameDatePage`のリストを生成して返す。（同期版）

    Wikidotへのリクエストは行わず、Crom APIから取得できるデータのみを使用。
    created_at等の情報はCrom APIに含まれないため、デフォルト値を使用する。

    Args:
        page_id: Wikidot ID

    Returns:
        日付ごとのAyameDatePageのリスト
    """
    crom_client = CromAPIClient()
    processor = RatingHistoryProcessor()

    # Crom APIからページ情報を取得
    crom_page = crom_client.get_page_by_wikidot_id(page_id)

    if crom_page is None:
        logger.warning(f"No Crom API data found for page id={page_id}")
        return []

    # Rating履歴を処理して日付ごとのページリストを生成
    date_pages = processor.generate_date_pages_from_crom_only(page_id, crom_page)

    return date_pages


async def get_date_pages_by_id(page_id: int) -> list[AyameDatePage]:
    """
    指定されたWikidot IDのページについて、Crom APIのみを使用して
    日付ごとの`AyameDatePage`のリストを生成して返す。（非同期版）

    Args:
        page_id: Wikidot ID

    Returns:
        日付ごとのAyameDatePageのリスト
    """
    return await asyncio.to_thread(_get_date_pages_by_id_sync, page_id)


if __name__ == "__main__":
    # Wikidot + Crom APIを使用するバージョンの時間測定
    print("=== Wikidot + Crom API版の測定 ===")
    start_time = time.time()
    data = _get_updated_data_sync(limit=1, hours=4)
    elapsed_wikidot = time.time() - start_time

    print(f"Fetched {len(data)} pages with history")
    print(f"Execution time: {elapsed_wikidot:.3f} seconds\n")

    print("Sample output:")
    for page_id, (date_pages, page_info) in data.items():
        test_page_id = page_id
        print(f"Page ID: {page_id}, Title: {page_info.fullname}")
        for date_page in date_pages:
            print(
                f"  Date: {date_page.date}, Rating: {date_page.rating}, MetaTitle: {date_page.metatitle}"
            )

    test_page_id = page_id

    # Crom APIのみを使用するバージョンの時間測定
    if test_page_id is not None:
        print(f"\n=== Crom APIのみ版の測定 (Page ID: {test_page_id}) ===")
        start_time = time.time()
        date_pages = _get_date_pages_by_id_sync(test_page_id)
        elapsed_crom_only = time.time() - start_time

        print(f"Execution time: {elapsed_crom_only:.3f} seconds\n")

        for date_page in date_pages:
            print(
                f"  Date: {date_page.date}, Rating: {date_page.rating}, MetaTitle: {date_page.metatitle}"
            )

        # 時間比較
        print(f"\n=== 時間比較 ===")
        print(f"Wikidot + Crom API: {elapsed_wikidot:.3f}秒")
        print(f"Crom APIのみ:      {elapsed_crom_only:.3f}秒")
        speedup = elapsed_wikidot / elapsed_crom_only if elapsed_crom_only > 0 else 0
        print(f"速度向上:          {speedup:.2f}倍")
