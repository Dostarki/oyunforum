import os

from pymongo import MongoClient


def main():
    client = MongoClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    result = db.agents.delete_many({"handle_key": {"$regex": r"^test_"}})
    print(f"deleted_test_agents={result.deleted_count}")
    client.close()


if __name__ == "__main__":
    main()
