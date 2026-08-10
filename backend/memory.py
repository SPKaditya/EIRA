"""Qdrant memory layer (per build-brief addendum).

Single collection, payload partitioning. user_id is a tenant-keyword index and
EVERY search/scroll/delete carries the user_id filter — no unfiltered queries
anywhere. Embedding at upsert and query goes through the models.Document
FastEmbed pattern (local inference, no manual encoding).
"""
import os
import time
import uuid

from qdrant_client import QdrantClient, models

COLLECTION = "eira_memory"
DENSE_MODEL = "BAAI/bge-small-en-v1.5"  # fastembed default, 384-dim
DENSE_DIM = 384

_client: QdrantClient | None = None


def client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            url=os.environ["QDRANT_URL"],
            api_key=os.getenv("QDRANT_API_KEY") or None,
        )
        _ensure_collection(_client)
    return _client


def _ensure_collection(c: QdrantClient) -> None:
    if not c.collection_exists(COLLECTION):
        c.create_collection(
            collection_name=COLLECTION,
            vectors_config=models.VectorParams(size=DENSE_DIM, distance=models.Distance.COSINE),
        )
    # idempotent: re-declaring an existing index is a no-op
    c.create_payload_index(
        collection_name=COLLECTION,
        field_name="user_id",
        field_schema=models.KeywordIndexParams(
            type=models.KeywordIndexType.KEYWORD, is_tenant=True
        ),
    )
    c.create_payload_index(
        collection_name=COLLECTION,
        field_name="type",
        field_schema=models.PayloadSchemaType.KEYWORD,
    )


def _doc(text: str) -> models.Document:
    return models.Document(text=text, model=DENSE_MODEL)


def _user_filter(user_id: str, extra: list | None = None) -> models.Filter:
    must = [models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id))]
    return models.Filter(must=must + (extra or []))


def _kind_cond(kind: str | None) -> list | None:
    if kind is None:
        return None
    return [models.FieldCondition(key="type", match=models.MatchValue(value=kind))]


def upsert(user_id: str, kind: str, text: str, extra: dict | None = None) -> str:
    """Store one memory. kind: task | preference | pattern_log | correction."""
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    payload = {
        "user_id": user_id,
        "type": kind,
        "text": text,
        "created_at": now,
        "updated_at": now,
        **(extra or {}),
    }
    pid = str(uuid.uuid4())
    client().upsert(
        collection_name=COLLECTION,
        points=[models.PointStruct(id=pid, vector=_doc(text), payload=payload)],
    )
    return pid


def search(user_id: str, query: str, limit: int = 4, kind: str | None = None) -> list[dict]:
    hits = client().query_points(
        collection_name=COLLECTION,
        query=_doc(query),
        query_filter=_user_filter(user_id, _kind_cond(kind)),
        limit=limit,
        with_payload=True,
    ).points
    return [{"id": h.id, "score": h.score, **(h.payload or {})} for h in hits]


def list_all(user_id: str, kind: str | None = None, limit: int = 100) -> list[dict]:
    points, _ = client().scroll(
        collection_name=COLLECTION,
        scroll_filter=_user_filter(user_id, _kind_cond(kind)),
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
    return [{"id": p.id, **(p.payload or {})} for p in points]


def update_payload(user_id: str, point_id, patch: dict) -> None:
    """Patch one point, filter-scoped to the user so a stray id can never
    touch another tenant's data."""
    patch = {**patch, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    client().set_payload(
        collection_name=COLLECTION,
        payload=patch,
        points=models.FilterSelector(
            filter=_user_filter(user_id, [models.HasIdCondition(has_id=[point_id])])
        ),
    )


def delete_matching(user_id: str, query: str, limit: int = 1) -> list[dict]:
    """Search this user's memories, delete best match(es), return what was removed.
    Deletion itself is filter-scoped to the user as a second guard."""
    hits = search(user_id, query, limit=limit)
    for h in hits:
        client().delete(
            collection_name=COLLECTION,
            points_selector=models.FilterSelector(
                filter=_user_filter(user_id, [models.HasIdCondition(has_id=[h["id"]])])
            ),
        )
    return hits


def wipe_user(user_id: str) -> None:
    client().delete(
        collection_name=COLLECTION,
        points_selector=models.FilterSelector(filter=_user_filter(user_id)),
    )
