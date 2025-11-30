import asyncio
import re

import motor.motor_asyncio


class database_class:
    def __init__(self):
        # mongodbの接続先
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(
            "mongodb://mongodb:27017"
        )
        # データベース名の宣言
        self.database_name = "ayame_api"
        # コレクション名の宣言
        self.c_data_name = "data_collection"
        self.c_search_name = "tag_search"
        self.c_update_date_name = "last_update_date"
        # キュー用コレクション名
        self.c_update_queue_name = "update_queue"

        # プログラム上で使用する
        self.database = self.db_client[self.database_name]
        self.collection_data = self.database[self.c_data_name]
        self.collection_search = self.database[self.c_search_name]
        self.collection_update_date = self.database[self.c_update_date_name]
        self.collection_update_queue = self.database[self.c_update_queue_name]

    async def create_index(self):
        """
        database上のインデックス作成
        """
        # 蓄積用コレクションのインデックス
        await self.collection_data.create_index("id")
        await self.collection_data.create_index("fullname")
        await self.collection_data.create_index("date")
        # 検索用コレクションのインデックス
        await self.collection_search.create_index("id")
        await self.collection_search.create_index("fullname")
        await self.collection_search.create_index("created_at")
        await self.collection_search.create_index("tags")
        await self.collection_search.create_index("metatitle")
        await self.collection_search.create_index("rating")
        await self.collection_search.create_index("author")
        # 更新キューインデックス
        await self.collection_update_queue.create_index(
            "page_id", unique=True
        )  # page_id単一管理
        await self.collection_update_queue.create_index(
            [("status", 1), ("priority", -1)]
        )  # 処理順用
        await self.collection_update_queue.create_index(
            [("status", 1), ("updated_at", 1)]
        )  # タイムアウト検出用

    async def database_compact(self):
        """
        databaseのデフラグ
        """
        await self.database.command({"compact": self.c_data_name})
        await self.database.command({"compact": self.c_search_name})


class mongodb_query_class(database_class):
    def __init__(self):
        database_class.__init__(self)

    def and_query(self, *queries):
        return {"$and": list(queries)}

    def or_query(self, *queries):
        return {"$or": list(queries)}

    def partial_match(self, field, value):
        """
        部分一致クエリ作成関数
        """
        return {field: {"$regex": re.escape(value)}}

    def prefix_match(self, field, value):
        """
        前方一致クエリ作成関数
        """
        return {field: {"$regex": f"^{re.escape(value)}"}}

    def backward_match(self, field, value):
        """
        後方一致クエリ作成関数
        """
        return {field: {"$regex": f"{re.escape(value)}$"}}

    def range_match(
        self,
        field,
        gte=None,
        lte=None,
    ):
        """
        gte = 以上
        lte = 以下
        gte <= x <= lte
        """
        if gte is None and lte is None:
            pass
        elif gte is not None and lte is None:
            return {field: {"$gte": gte}}
        elif gte is None and lte is not None:
            return {field: {"$lte": lte}}
        elif gte is not None and lte is not None:
            return {field: {"$gte": gte, "$lte": lte}}

    def perfect_match(self, field, value):
        return {field: value}

    def all_document(self):
        return {}


mongodb_query = mongodb_query_class()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    query1 = mongodb_query.partial_match("fullname", "scp")
    query2 = mongodb_query.prefix_match("meta", "123")

    test = mongodb_query.and_query(query1, query2)
    print(test)
    # result = loop.run_until_complete(test)
    # print(result)
