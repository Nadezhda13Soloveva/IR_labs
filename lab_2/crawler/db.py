from __future__ import annotations

import time
from typing import Any, Optional

from pymongo import ASCENDING, MongoClient, ReturnDocument
from pymongo.collection import Collection
from pymongo.database import Database


class Storage:
    def __init__(self, cfg: dict[str, Any]) -> None:
        db_cfg = cfg["db"]
        self.client = MongoClient(db_cfg["uri"])
        self.db: Database = self.client[db_cfg["database"]]
        self.documents: Collection = self.db[db_cfg["documents"]]
        self.frontier: Collection = self.db[db_cfg["frontier"]]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        self.documents.create_index("url", unique=True)
        self.documents.create_index("source")
        self.documents.create_index("crawled_at")
        self.documents.create_index("content_hash")

        self.frontier.create_index("url", unique=True)
        self.frontier.create_index([("status", ASCENDING), ("enqueued_at", ASCENDING)])
        self.frontier.create_index("source")

    def enqueue(
        self,
        url: str,
        source: str,
        *,
        status: str = "pending",
        force_pending: bool = False,
    ) -> bool:
        """
        добавить URL в очередь
        return: True - документ новый или принудительно вернули в pending
        """
        now = int(time.time())
        existing = self.frontier.find_one({"url": url})
        if existing is None:
            self.frontier.insert_one(
                {
                    "url": url,
                    "source": source,
                    "status": status,
                    "enqueued_at": now,
                    "errors": 0,
                    "last_error": None,
                }
            )
            return True

        if force_pending and existing.get("status") != "pending":
            self.frontier.update_one(
                {"url": url},
                {
                    "$set": {
                        "status": "pending",
                        "enqueued_at": now,
                        "last_error": None,
                    }
                },
            )
            return True
        return False

    def claim_next_pending(self) -> Optional[dict[str, Any]]:
        """взять следующий pending URL"""
        return self.frontier.find_one_and_update(
            {"status": "pending"},
            {"$set": {"status": "in_progress", "started_at": int(time.time())}},
            sort=[("enqueued_at", ASCENDING)],
            return_document=ReturnDocument.AFTER,
        )

    def mark_done(self, url: str) -> None:
        self.frontier.update_one(
            {"url": url},
            {"$set": {"status": "done", "finished_at": int(time.time())}},
        )

    def mark_error(self, url: str, error: str, max_errors: int) -> None:
        doc = self.frontier.find_one({"url": url})
        errors = int(doc.get("errors", 0)) + 1 if doc else 1
        status = "error" if errors >= max_errors else "pending"
        self.frontier.update_one(
            {"url": url},
            {
                "$set": {
                    "status": status,
                    "errors": errors,
                    "last_error": error[:500],
                    "enqueued_at": int(time.time()),  # в конец очереди при retry
                }
            },
        )

    def recover_in_progress(self) -> int:
        """после падения процесса вернуть in_progress обратно в pending"""
        result = self.frontier.update_many(
            {"status": "in_progress"},
            {"$set": {"status": "pending"}},
        )
        return result.modified_count

    def pending_count(self) -> int:
        return self.frontier.count_documents({"status": "pending"})

    def frontier_empty(self) -> bool:
        return self.frontier.count_documents({}) == 0


    # documents

    def documents_count(self) -> int:
        return self.documents.count_documents({})

    def get_document(self, url: str) -> Optional[dict[str, Any]]:
        return self.documents.find_one({"url": url})

    def upsert_document(
        self,
        *,
        url: str,
        source: str,
        raw_html: str,
        content_hash: str,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
    ) -> None:
        now = int(time.time())
        self.documents.update_one(
            {"url": url},
            {
                "$set": {
                    "url": url,
                    "source": source,
                    "raw_html": raw_html,
                    "crawled_at": now,
                    "content_hash": content_hash,
                    "etag": etag,
                    "last_modified": last_modified,
                }
            },
            upsert=True,
        )

    def touch_crawled_at(self, url: str) -> None:
        """документ не изменился - только обновить время проверки"""
        self.documents.update_one(
            {"url": url},
            {"$set": {"crawled_at": int(time.time())}},
        )

    def stale_urls(self, older_than_ts: int, limit: int = 100) -> list[dict[str, Any]]:
        """документы, которые пора перепроверить"""
        cursor = (
            self.documents.find(
                {"crawled_at": {"$lt": older_than_ts}},
                {"url": 1, "source": 1},
            )
            .sort("crawled_at", ASCENDING)
            .limit(limit)
        )
        return list(cursor)

    def close(self) -> None:
        self.client.close()
