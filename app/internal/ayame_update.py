import asyncio
import copy
import datetime
import json
import random
import string

import aiofiles
import dateutil.parser

from app.data_update.get_updated import get_updated_data, get_date_pages_by_id

from .command import command_run
from .database import mongodb_query
from .logger import logger


class ayame_update_class:
    def __init__(self):
        self.updating = False
        pass

    def same_dictionary_check(self, dict1, dict2, exclusion_key_list=["date", "_id"]):
        """
        辞書が同じならTrue
        """
        # 辞書の独立化
        copy_dict1, copy_dict2 = copy.deepcopy(dict1), copy.deepcopy(dict2)
        # 除外キーを比較用の辞書から削除
        for exclusion_key in exclusion_key_list:
            if exclusion_key in copy_dict1:
                del copy_dict1[exclusion_key]
            if exclusion_key in copy_dict2:
                del copy_dict2[exclusion_key]
        if copy_dict1 == copy_dict2:
            return True
        else:
            return False

    def get_today(self):
        JST = datetime.timezone(datetime.timedelta(hours=+9), "JST")
        dt_now = datetime.datetime.now(JST)
        return str(dt_now.date())

    def randomname(self, n):
        return "".join(random.choices(string.ascii_letters + string.digits, k=n))

    def get_update_password(self):
        password_file = "password.txt"
        password = None
        try:
            with open(password_file) as f:
                password = f.read()
        except BaseException:
            password = str(self.randomname(10))
            f = open(password_file, "w")
            f.write(password)
            f.close()
        return password

    async def load_json_data(self, filepath="ayame/data/data.json"):
        async with aiofiles.open(filepath, mode="r") as f:
            json_contents = await f.read()
        return json.loads(str(json_contents))

    async def sync_json_data(self):
        result = await command_run("python3 src/create_json.py", "/ayame/ayame")
        if result.returncode == 0:
            logger.info(result.stdout)
            return True
        else:
            logger.warning("sync data fail")
            logger.warning(result.stdout)
            logger.warning(result.stderr)
            return False

    async def update_database(self):
        logger.info("データベース更新開始")
        self.updating = True
        # インデックスの確認・作成
        await mongodb_query.create_index()

        # 直近4時間以内に更新されたページのデータ取得
        try:
            updated = await get_updated_data(limit=120, hours=4)
        except Exception as e:
            logger.error(f"get_updated_data failed: {e}")
            self.updating = False
            return False

        # ページごとに履歴（vote）をcollection_dataへ、最新情報をcollection_searchへ反映
        for page_id, (date_pages, page_info) in updated.items():
            # 履歴投入: id + date で存在チェックして追加 or 置換
            for item in date_pages:
                doc = item.model_dump()
                new_document = self.convert_docment_type(doc)

                # id/date複合条件で検索
                q_id = mongodb_query.perfect_match("id", new_document["id"])
                q_date = mongodb_query.perfect_match("date", new_document["date"])
                query = mongodb_query.and_query(q_id, q_date)
                exist = await mongodb_query.collection_data.find_one(query)

                if exist is None:
                    await mongodb_query.collection_data.insert_one(new_document)
                else:
                    # 差分がある場合のみ置換
                    if not self.same_dictionary_check(exist, new_document):
                        await mongodb_query.collection_data.replace_one(
                            mongodb_query.perfect_match("_id", exist["_id"]),
                            new_document,
                        )

            # 最新情報の検索用コレクション更新（常に最新のWikidotデータ）
            latest_doc = page_info.model_dump()
            latest_doc["id"] = page_id
            latest_doc["date"] = self.get_today()
            # Cromのタイトルをメタタイトルとして格納（取得済み履歴から拝借）
            if len(date_pages) > 0:
                latest_doc["metatitle"] = date_pages[-1].metatitle

            latest_doc = self.convert_docment_type(latest_doc)
            await self.update_collection_search(latest_doc)

        await mongodb_query.database_compact()
        self.updating = False
        return True

    async def partial_update_from_crom(self, page_id: int) -> bool:
        """Crom APIのみを用いて指定page_idのrating/date/tags/metatitleを部分更新。

        既存ドキュメントがなければ最低限のフィールドで作成。
        履歴(dateごと)は collection_data に挿入（既存差分のみ）。
        検索用 collection_search は該当フィールドのみ $set 更新。
        """
        try:
            # Cromから日付別rating履歴を取得
            date_pages = await get_date_pages_by_id(page_id)
        except Exception as e:
            logger.error(f"Crom partial fetch failed page_id={page_id}: {e}")
            return False

        if len(date_pages) == 0:
            logger.warning(f"No Crom data for page_id={page_id}")
            return False

        # collection_data へ: 各dateで存在しない or rating差分あれば挿入
        for d in date_pages:
            base_doc = {
                "id": d.id,
                "date": d.date,
                "rating": d.rating,
                "metatitle": d.metatitle,
                "tags": d.tags,
            }
            q_id = mongodb_query.perfect_match("id", d.id)
            q_date = mongodb_query.perfect_match("date", d.date)
            query = mongodb_query.and_query(q_id, q_date)
            exist = await mongodb_query.collection_data.find_one(query, {"rating": 1})
            if exist is None or exist.get("rating") != d.rating:
                await mongodb_query.collection_data.insert_one(base_doc)

        # collection_search へ: 部分的に $set
        q_search = mongodb_query.perfect_match("id", page_id)
        latest = date_pages[-1]
        update_fields = {
            "rating": latest.rating,
            "metatitle": latest.metatitle,
            "tags": latest.tags,
            "date": latest.date,
            "last_partial_at": datetime.datetime.now(datetime.timezone.utc),
        }
        exist_search = await mongodb_query.collection_search.find_one(q_search)
        if exist_search is None:
            # 新規作成（他フィールドは空）
            new_doc = {
                "id": page_id,
                "fullname": latest.fullname,
                "title": latest.title or latest.metatitle,
                **update_fields,
            }
            await mongodb_query.collection_search.insert_one(new_doc)
        else:
            await mongodb_query.collection_search.update_one(
                q_search, {"$set": update_fields}
            )
        return True

    async def process_partial_queue(self, batch_size: int = 20) -> dict:
        """pendingキューを処理してCrom部分更新を実施
        update_queueモジュールは実行時インポートでパス問題を回避
        """
        from importlib import import_module

        uq = import_module("app.internal.update_queue")
        result = {"processed": 0, "failed": 0}
        pending_ids = await uq.get_pending(batch_size=batch_size)
        for page_id in pending_ids:
            await uq.mark_processing(page_id)
            ok = await self.partial_update_from_crom(page_id)
            if ok:
                await uq.mark_completed(page_id)
                result["processed"] += 1
            else:
                await uq.mark_failed(page_id, "partial_update_failed")
                result["failed"] += 1
        if result["processed"] or result["failed"]:
            logger.info(
                f"partial queue processed={result['processed']} failed={result['failed']}"
            )
        return result

    async def update_database_document(self, new_document):
        # 2つのデータベースを更新する
        tasks = []
        tasks.append(self.update_collection_data(new_document))
        tasks.append(self.update_collection_search(new_document))
        await asyncio.gather(*tasks)

    async def update_collection_data(self, new_document):
        """
        collection_dataの更新
        全区間保有データベースの更新
        """
        new_document = copy.deepcopy(new_document)

        # idキーの存在確認
        if "id" not in new_document:
            logger.warning(f"Document missing 'id' key, skipping: {new_document}")
            return

        # idから全区間データベース内の最新ドキュメントを取得し
        # それが実行時の日付でなければ新規作成を行い、あれば更新を行う。
        query = mongodb_query.perfect_match("id", new_document["id"])
        sort = [("date", -1)]
        document = await mongodb_query.collection_data.find_one(query, sort=sort)

        if document is None:
            # 新しいデータ
            await mongodb_query.collection_data.insert_one(new_document)
        elif self.same_dictionary_check(document, new_document):
            # 前回の取得データと変わらないときは何もしない
            pass
        else:
            # データが更新されている場合は追加
            await mongodb_query.collection_data.insert_one(new_document)

        return

    async def update_collection_search(self, new_document):
        """
        collection_searchの更新
        検索用データベースの更新
        """
        new_document = copy.deepcopy(new_document)

        # idキーの存在確認
        if "id" not in new_document:
            logger.warning(f"Document missing 'id' key, skipping: {new_document}")
            return

        # 現存するドキュメントを取得し、あれば更新なければ新規作成をする
        query = mongodb_query.perfect_match("id", new_document["id"])
        document = await mongodb_query.collection_search.find_one(query)
        if document is None:
            # 存在しない場合新規追加
            await mongodb_query.collection_search.insert_one(new_document)
        else:
            # 存在する場合入れ替え
            query = mongodb_query.perfect_match("_id", document["_id"])
            await mongodb_query.collection_search.replace_one(query, new_document)
        return

    async def update_lock(self):
        new_document = {"name": "update_status", "status": "updating"}
        query = mongodb_query.perfect_match("name", "update_status")
        document = await mongodb_query.collection_update_date.find_one(query)
        if document:
            await mongodb_query.collection_update_date.replace_one(query, new_document)
        else:
            await mongodb_query.collection_update_date.insert_one(new_document)

    async def update_unlock(self):
        new_document = {"name": "update_status", "status": "stop"}
        query = mongodb_query.perfect_match("name", "update_status")
        document = await mongodb_query.collection_update_date.find_one(query)
        if document:
            await mongodb_query.collection_update_date.replace_one(query, new_document)
        else:
            await mongodb_query.collection_update_date.insert_one(new_document)

    def convert_docment_type(self, document):
        doc = copy.deepcopy(document)
        date_keys = ["created_at", "updated_at", "commented_at"]
        int_keys = [
            "size",
            "rating",
            "rating_votes",
            "comments",
            "revisions",
            "created_by_id",
            "updated_by_id",
            "commented_by_id",
            "id",
            "article_id",
        ]
        list_keys = ["tags"]
        if "article_id" in doc.keys():
            doc["id"] = doc["article_id"]
        for key in doc:
            val = doc[key]
            # 空文字やNoneを正規化
            if val in ("", None):
                if key in list_keys:
                    doc[key] = []
                elif key in date_keys:
                    doc[key] = None
                # その他のキーはそのままNone/空扱いでスキップ
                continue
            # 型変換
            if key in date_keys and not isinstance(val, datetime.datetime):
                try:
                    doc[key] = dateutil.parser.parse(str(val))
                except Exception:
                    # 解析できない場合はスキップ
                    pass
            elif key in int_keys and not isinstance(val, int):
                try:
                    doc[key] = int(val)
                except Exception:
                    pass
            elif key in list_keys and not isinstance(val, list):
                doc[key] = str(val).split(" ")

        return doc

    async def convert_database_type(self):
        collections = [mongodb_query.collection_data, mongodb_query.collection_search]

        for collection in collections:
            query = mongodb_query.all_document()
            cursor = collection.find(query)
            count = 0
            async for document in cursor:
                try:
                    new_document = self.convert_docment_type(document)
                    # databaseの内部IDは削除
                    del new_document["_id"]
                    query = mongodb_query.perfect_match("_id", document["_id"])
                    await collection.replace_one(query, new_document)
                    count += 1
                except BaseException:
                    print(count)
                    break
        return


ayame_update = ayame_update_class()


if __name__ == "__main__":
    # import json

    doc = {}
    ayame_update.convert_docment_type(doc)
