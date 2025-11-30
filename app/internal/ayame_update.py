import asyncio
import copy
import datetime
import json
import random
import string

import aiofiles
import dateutil.parser

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
        # if self.updating:
        #    return False
        self.updating = True
        result = await self.sync_json_data()
        if result:
            pass
        else:
            logger.error("更新エラー")
            self.updating = False
            return False
        await mongodb_query.create_index()
        new_documents = await self.load_json_data()
        for document in new_documents:
            # 入力されるドキュメントのデータ型を整形
            new_document = self.convert_docment_type(document)
            # 実行した日付を追加
            new_document["date"] = self.get_today()
            await self.update_database_document(new_document)
        await mongodb_query.database_compact()
        self.updating = False
        return True

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
            if "" == doc[key]:
                if key in list_keys:
                    doc[key] = list()
            else:
                if key in date_keys:
                    doc[key] = dateutil.parser.parse(str(doc[key]))
                elif key in int_keys and not isinstance(doc[key], int):
                    doc[key] = int(doc[key])
                elif key in list_keys and not isinstance(doc[key], list):
                    doc[key] = doc[key].split(" ")

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
