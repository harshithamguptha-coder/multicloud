from urllib.parse import urlsplit

import certifi
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConfigurationError, ConnectionFailure, PyMongoError, ServerSelectionTimeoutError

from config import Config


def validate_mongo_uri(mongo_uri: str) -> str:
    if not mongo_uri:
        raise RuntimeError("MONGO_URI is missing.")
    if not mongo_uri.startswith("mongodb+srv://"):
        raise RuntimeError("MongoDB Atlas requires a mongodb+srv:// URI.")

    parsed = urlsplit(mongo_uri)
    database_name = parsed.path.lstrip("/")
    if not database_name:
        raise RuntimeError("MONGO_URI must include a database name, for example /multicloud_integrity.")

    return database_name


def main():
    load_dotenv()
    database_name = validate_mongo_uri(Config.MONGO_URI)

    try:
        client = MongoClient(
            Config.MONGO_URI,
            tls=True,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=20000,
            connectTimeoutMS=20000,
            socketTimeoutMS=20000,
            appname="atlas-ping-check",
        )
        client.admin.command("ping")
        db = client.get_database(database_name)
        print(f"Connected to Atlas database: {database_name}")
        print("Collections:", db.list_collection_names())
        client.close()
    except (ConfigurationError, ConnectionFailure, ServerSelectionTimeoutError) as exc:
        raise SystemExit(f"MongoDB Atlas connection failed: {exc}") from exc
    except PyMongoError as exc:
        raise SystemExit(f"MongoDB Atlas error: {exc}") from exc


if __name__ == "__main__":
    main()
