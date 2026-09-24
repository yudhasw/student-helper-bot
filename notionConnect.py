import os
import httpx
from dotenv import load_dotenv

load_dotenv()

NOTION_TOKEN = os.environ["NOTION_TOKEN"].strip()
TASKS_DB_ID = os.environ["NOTION_TASKS_DB_ID"].strip()

_client = httpx.AsyncClient(
    base_url="https://api.notion.com/v1",
    headers={
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    },
    timeout=10,
)


async def list_open_tasks():
    r = await _client.post(
        f"/databases/{TASKS_DB_ID}/query",
        json={
            "filter": {"property": "Status", "status": {"does_not_equal": "Selesai"}},
            "sorts": [{"property": "Deadline", "direction": "ascending"}],
        },
    )
    r.raise_for_status()
    return r.json()["results"]


async def add_task(name: str, deadline: str | None = None):
    props = {
        "Name": {"title": [{"text": {"content": name}}]},
        "Status": {"status": {"name": "Belum"}},
        "Source": {"select": {"name": "Telegram"}},
    }
    if deadline:
        props["Deadline"] = {"date": {"start": deadline}}
    r = await _client.post(
        "/pages", json={"parent": {"database_id": TASKS_DB_ID}, "properties": props}
    )
    r.raise_for_status()
    return r.json()


async def mark_done(page_id: str):
    r = await _client.patch(
        f"/pages/{page_id}",
        json={"properties": {"Status": {"status": {"name": "Selesai"}}}},
    )
    r.raise_for_status()
