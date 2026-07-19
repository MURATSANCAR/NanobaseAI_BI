from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from fingerprint import point_id_from_key
from models import SchemaDocument


def _http_json(
    method: str,
    url: str,
    body: dict | None = None,
    headers: dict | None = None,
    timeout: int = 120,
) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> {e.code}: {raw[:600]}") from e


class QdrantWriter:
    def __init__(self, base_url: str, collection: str, vector_size: int = 1024):
        self.base = base_url.rstrip("/")
        self.collection = collection
        self.vector_size = vector_size

    def ensure_collection(self, *, recreate: bool = False) -> None:
        url = f"{self.base}/collections/{self.collection}"
        exists = False
        try:
            _http_json("GET", url)
            exists = True
        except RuntimeError:
            exists = False
        if exists and recreate:
            _http_json("DELETE", url)
            exists = False
        if not exists:
            _http_json(
                "PUT",
                url,
                {"vectors": {"size": self.vector_size, "distance": "Cosine"}},
            )

    def existing_fingerprints(self, datasource_id: str) -> dict[str, str]:
        out: dict[str, str] = {}
        offset = None
        while True:
            body: dict[str, Any] = {
                "limit": 256,
                "with_payload": ["document_key", "fingerprint", "datasource_id"],
                "with_vector": False,
                "filter": {
                    "must": [{"key": "datasource_id", "match": {"value": datasource_id}}]
                },
            }
            if offset is not None:
                body["offset"] = offset
            try:
                res = _http_json(
                    "POST",
                    f"{self.base}/collections/{self.collection}/points/scroll",
                    body,
                )
            except RuntimeError:
                return out
            result = res.get("result") or {}
            for pt in result.get("points") or []:
                payload = pt.get("payload") or {}
                key = payload.get("document_key")
                fp = payload.get("fingerprint")
                if key and fp:
                    out[str(key)] = str(fp)
            offset = result.get("next_page_offset")
            if offset is None:
                break
        return out

    def existing_point_ids(self, datasource_id: str) -> dict[str, int]:
        out: dict[str, int] = {}
        offset = None
        while True:
            body: dict[str, Any] = {
                "limit": 256,
                "with_payload": ["document_key", "datasource_id"],
                "with_vector": False,
                "filter": {
                    "must": [{"key": "datasource_id", "match": {"value": datasource_id}}]
                },
            }
            if offset is not None:
                body["offset"] = offset
            try:
                res = _http_json(
                    "POST",
                    f"{self.base}/collections/{self.collection}/points/scroll",
                    body,
                )
            except RuntimeError:
                return out
            result = res.get("result") or {}
            for pt in result.get("points") or []:
                payload = pt.get("payload") or {}
                key = payload.get("document_key")
                if key:
                    out[str(key)] = int(pt["id"])
            offset = result.get("next_page_offset")
            if offset is None:
                break
        return out

    def upsert(self, docs: list[SchemaDocument], vectors: list[list[float]]) -> int:
        points = []
        for doc, vec in zip(docs, vectors):
            pid = int(doc.payload.get("point_id") or point_id_from_key(doc.document_key))
            points.append({"id": pid, "vector": vec, "payload": doc.payload})
        for i in range(0, len(points), 64):
            batch = points[i : i + 64]
            _http_json(
                "PUT",
                f"{self.base}/collections/{self.collection}/points?wait=true",
                {"points": batch},
            )
        return len(points)

    def delete_keys(self, document_keys: list[str]) -> int:
        if not document_keys:
            return 0
        ids = [point_id_from_key(k) for k in document_keys]
        for i in range(0, len(ids), 64):
            batch = ids[i : i + 64]
            _http_json(
                "POST",
                f"{self.base}/collections/{self.collection}/points/delete?wait=true",
                {"points": batch},
            )
        return len(ids)

    def points_count(self) -> int | None:
        try:
            info = _http_json("GET", f"{self.base}/collections/{self.collection}")
            return int((info.get("result") or {}).get("points_count") or 0)
        except RuntimeError:
            return None
