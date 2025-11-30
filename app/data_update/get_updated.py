import pathlib
import sys
from datetime import timezone

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


def get_updated_data(
    limit: int = 120, hours: int = 4
) -> dict[int, tuple[list[AyameDatePage], PageInfo]]:
    """
    最近編集（updated_at）のページを取得し、Cromの投票履歴から
    日付ごとの`AyameDatePage`のリストを生成して返す。

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


if __name__ == "__main__":
    # 手動実行時の簡易出力（同期のみ）
    data = get_updated_data(limit=20, hours=4)
    print(f"Fetched {len(data)} pages with history (sync)")
