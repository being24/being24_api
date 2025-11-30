import json

from .database import mongodb_query


class ayame_fix_class:
    def __init__(self):
        pass

    def load_fix_pageids(self):
        with open("ayame/data/fix_page_ids.json") as f:
            df = json.load(f)
        return df

    async def test(self):
        fix_pageids = self.load_fix_pageids()
        count = 0
        for fullname in fix_pageids:
            count += 1
            if count % 100 == 0:
                print("進行中", count)
            pageid = int(fix_pageids[fullname])

            collection = mongodb_query.collection_data
            query = mongodb_query.perfect_match("fullname", fullname)
            update = await collection.update_many(query, {"$set": {"id": pageid}})

            collection = mongodb_query.collection_search
            query = mongodb_query.perfect_match("fullname", fullname)
            update = await collection.update_many(query, {"$set": {"id": pageid}})


ayame_fix = ayame_fix_class()
