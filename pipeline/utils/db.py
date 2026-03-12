import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        _client = create_client(url, key)
    return _client


def insert(table: str, data: dict | list[dict]) -> list[dict]:
    client = get_client()
    result = client.table(table).insert(data).execute()
    return result.data


def upsert(table: str, data: dict | list[dict], on_conflict: str = "id") -> list[dict]:
    client = get_client()
    result = client.table(table).upsert(data, on_conflict=on_conflict).execute()
    return result.data


def select(table: str, filters: dict | None = None, limit: int = 1000) -> list[dict]:
    client = get_client()
    query = client.table(table).select("*").limit(limit)
    if filters:
        for key, value in filters.items():
            query = query.eq(key, value)
    return query.execute().data


def update(table: str, match: dict, data: dict) -> list[dict]:
    client = get_client()
    query = client.table(table).update(data)
    for key, value in match.items():
        query = query.eq(key, value)
    return query.execute().data
