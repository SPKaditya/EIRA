# Qdrant — Complete Reference

> Condensed from https://qdrant.tech/documentation/ (current as of 2026-08-10, docs ~v1.19) and the
> https://github.com/qdrant/qdrant repository, for the EIRA hackathon project.
> Qdrant is an open-source (Apache-2.0, Rust) vector database and similarity search engine:
> dense/sparse/multi-vector search with payload filtering, hybrid queries, and quantization,
> served over REST (port 6333) and gRPC (6334), locally via Docker or managed on Qdrant Cloud.

## Contents

- **Part 1 — Fundamentals, Quickstart & Repo**: what Qdrant is, distance metrics, Docker install, local + cloud quickstarts, Web UI, SDKs, repo facts (v1.19.0)
- **Part 2 — Data Management**: collections, points, dense/sparse/multi-vectors, payload, indexing (HNSW + payload + full-text), storage/WAL, quantization, multitenancy, bulk upload
- **Part 3 — Search**: Query API, every filter condition, hybrid queries (prefetch, RRF/DBSF fusion, ColBERT rescoring), recommend/discover/context, full-text, MMR, search-time tuning
- **Part 4 — Embeddings & Tooling**: cloud Inference API, FastEmbed (dense/sparse/late-interaction/rerankers), MCP server, Agent Skills, Qdrant Edge
- **Part 5 — Operations, Cloud, Tutorials & Integrations**: auth/TLS/JWT, config, optimization, snapshots, distributed deployment, monitoring, Cloud free tier, tutorial patterns, LangChain/LlamaIndex/Haystack/CrewAI, migrations

---


# Part 1 — Qdrant Fundamentals, Quickstart & Repo

## What is Qdrant

- Vector similarity search engine and vector database: "a production-ready service with a convenient API to store, search, and manage points — vectors with an additional payload."
- Written in **Rust** (fast and reliable under high load). License: **Apache 2.0**.
- Core data model:
  - **Collection** — named set of points; all vectors in a (default) vector config share the same dimensionality and distance metric. Named vectors allow multiple vectors per point (each with its own size/metric).
  - **Point** — the central unit: `id` + `vector` + optional JSON `payload` (metadata).
  - **Payload** — arbitrary JSON attached to a point; filterable with rich conditions.
- Indexing: **HNSW** graph for approximate nearest neighbor (ANN) search → sublinear search time (compares against a subset of the DB, not all points).
- Key features (from GitHub README): dense, sparse, and multivector search; payload filtering (JSON, rich conditions); hybrid search with configurable fusion; vector quantization (up to ~97% RAM reduction); distributed deployment (sharding + replication); faceting, recommendation, discovery APIs; multitenancy; GPU-accelerated indexing (NVIDIA and AMD); write-ahead logging for persistence; built-in Web UI.
- Storage tiers: `pinned` (full RAM), `cached` (warm disk cache), `cold` (RAM-efficient, on-disk).

## Vector search basics

- Dense embeddings are produced by neural encoders (HuggingFace models, SentenceTransformers, SaaS APIs like Cohere co.embed); they "capture the meaning, not the words" — handle synonyms and multilingual text.
- Dense vectors: relatively low dimensionality (hundreds to a few thousand dims), contrasted with sparse keyword-derived vectors.
- Search = nearest-neighbor lookup by embedding similarity; HNSW makes it approximate but fast; filters can constrain the candidate set ("search is performed only among those points that satisfy the filter condition").

## Distance metrics

| Metric (API value) | Formula | Measures | Typical use |
|---|---|---|---|
| `Cosine` | `(A·B)/(‖A‖‖B‖)` | direction only; range 1 → 0 → −1 | NLP, semantic search (default choice when unsure) |
| `Dot` | `Σ Aᵢ·Bᵢ` | magnitude + direction | recommendations, ranking |
| `Euclid` (L2) | `√Σ(Aᵢ−Bᵢ)²` | absolute distance; scale-sensitive | spatial data, anomaly detection |
| `Manhattan` (L1) | `Σ|Aᵢ−Bᵢ|` | grid distance; robust to outliers | sparse/tabular data |

- Qdrant implements Cosine as **dot product over normalized vectors**; vectors are auto-normalized at upload time when the collection metric is `Cosine`.
- Normalized-to-unit-length vectors ⇒ dot product ≡ cosine similarity.
- Different metrics can be set per named vector in one collection (useful for A/B tests).

## Installation

### Docker (canonical)

```bash
docker pull qdrant/qdrant

docker run -p 6333:6333 -p 6334:6334 \
    -v "$(pwd)/qdrant_storage:/qdrant/storage:z" \
    qdrant/qdrant
```

With custom config:

```bash
docker run -p 6333:6333 \
    -v $(pwd)/path/to/data:/qdrant/storage \
    -v $(pwd)/path/to/custom_config.yaml:/qdrant/config/production.yaml \
    qdrant/qdrant
```

### docker-compose

```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    restart: always
    container_name: qdrant
    ports:
      - 6333:6333
      - 6334:6334
    expose:
      - 6333
      - 6334
      - 6335
    volumes:
      - ./qdrant_data:/qdrant/storage
```

### Ports

| Port | Purpose |
|---|---|
| **6333** | REST/HTTP API, Web UI, monitoring, health checks |
| **6334** | gRPC API |
| **6335** | inter-node communication in distributed deployments |

### Paths & config

- Data: `/qdrant/storage` (inside container).
- Config file: `/qdrant/config/production.yaml`.
- Storage must be block-level, POSIX-compatible filesystem; SSD/NVMe recommended. **NFS / S3 / network filesystems are not supported.**

### From source / other

- Build with Rust toolchain: `cargo build --release --bin qdrant` → binary at `./target/release/qdrant`.
- Architectures: x86_64/amd64 and AArch64/arm64 (64-bit only).
- Production options: Qdrant Cloud (managed), Kubernetes Operator (enterprise), community Helm chart, plain Docker/Compose (manual HA/backup/monitoring).
- Defaults of note: HNSW `m: 16`, `ef_construct: 100`, `full_scan_threshold: 10000`, `max_indexing_threads: 0`; `on_disk_payload: false`.

## Local quickstart (Python)

```bash
pip install qdrant-client
```

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

client = QdrantClient(url="http://localhost:6333")

client.create_collection(
    collection_name="test_collection",
    vectors_config=VectorParams(size=4, distance=Distance.DOT),
)

client.upsert(
    collection_name="test_collection",
    wait=True,
    points=[
        PointStruct(id=1, vector=[0.05, 0.61, 0.76, 0.74], payload={"city": "Berlin"}),
        PointStruct(id=2, vector=[0.19, 0.81, 0.75, 0.11], payload={"city": "London"}),
        PointStruct(id=3, vector=[0.36, 0.55, 0.47, 0.94], payload={"city": "Moscow"}),
        PointStruct(id=4, vector=[0.18, 0.01, 0.85, 0.80], payload={"city": "New York"}),
        PointStruct(id=5, vector=[0.24, 0.18, 0.22, 0.44], payload={"city": "Beijing"}),
        PointStruct(id=6, vector=[0.35, 0.08, 0.11, 0.44], payload={"city": "Mumbai"}),
    ],
)

search_result = client.query_points(
    collection_name="test_collection",
    query=[0.2, 0.1, 0.9, 0.7],
    with_payload=False,
    limit=3,
).points

# Filtered search
from qdrant_client.models import Filter, FieldCondition, MatchValue

search_result = client.query_points(
    collection_name="test_collection",
    query=[0.2, 0.1, 0.9, 0.7],
    query_filter=Filter(must=[FieldCondition(key="city", match=MatchValue(value="London"))]),
    with_payload=True,
    limit=3,
).points
```

## REST equivalents (curl)

Create collection:

```bash
curl -X PUT http://localhost:6333/collections/test_collection \
  -H 'Content-Type: application/json' \
  --data-raw '{
    "vectors": { "size": 4, "distance": "Dot" }
  }'
```

Upsert points (`PUT /collections/{collection_name}/points`):

```bash
curl -X PUT http://localhost:6333/collections/test_collection/points \
  -H 'Content-Type: application/json' \
  --data-raw '{
    "points": [
      {"id": 1, "vector": [0.9, 0.1, 0.1], "payload": {"color": "red"}},
      {"id": 2, "vector": [0.1, 0.9, 0.1], "payload": {"color": "green"}},
      {"id": 3, "vector": [0.1, 0.1, 0.9], "payload": {"color": "blue"}}
    ]
  }'
```

Query (`POST /collections/{collection_name}/points/query`):

```bash
curl -X POST http://localhost:6333/collections/test_collection/points/query \
  -H 'Content-Type: application/json' \
  --data-raw '{
    "query": [0.2, 0.1, 0.9, 0.7],
    "limit": 3
  }'
```

Filtered query with search params:

```json
POST /collections/{collection_name}/points/query
{
    "query": [0.2, 0.1, 0.9, 0.7],
    "filter": { "must": [ { "key": "city", "match": { "value": "London" } } ] },
    "params": { "hnsw_ef": 128, "exact": false },
    "limit": 3
}
```

- Point IDs: **64-bit unsigned integers** or **UUID strings** (simple `936DA01F...`, hyphenated `550e8400-e29b-41d4-a716-446655440000`, or URN `urn:uuid:...`); both types can be mixed in one request.

## Cloud quickstart

1. Register at cloud.qdrant.io (email, Google, or GitHub).
2. Enter cluster name, pick provider + region, click **Create Free Cluster** (free tier exists).
3. **Copy the API key when prompted — it is shown only once.**

```python
from qdrant_client import QdrantClient

client = QdrantClient(
    url="https://xyz-example.eu-central.aws.cloud.qdrant.io",  # cluster URL pattern
    api_key="your-api-key",
    cloud_inference=True,  # optional: server-side embedding via Cloud Inference
)
```

Connectivity check:

```bash
curl -X GET 'https://<your-cluster-host>:6333/collections' \
  --header 'api-key: <api-key-value>'
```

- Cloud Inference offers free embedding models, e.g. `sentence-transformers/all-MiniLM-L6-v2`; model list is on the cluster's Inference tab in the Cloud Console.
- Cloud clusters are secure by default; **self-hosted Qdrant has no auth until you configure it**.

## Web UI

- Local: `http://localhost:6333/dashboard`. Cloud: cluster URL + `:6333/dashboard`.
- Features: REST console (issue API calls from the browser), collection list/search/management, snapshot upload, interactive tutorial at `http://localhost:6333/dashboard#/tutorial`.

## API & SDKs

- **REST (6333)**: easiest to debug; recommended for prototypes. **gRPC (6334)**: binary, faster; "trade-off between convenience and speed."
- REST spec: https://api.qdrant.tech/api-reference (OpenAPI). gRPC: protobuf defs at `github.com/qdrant/qdrant/tree/master/lib/api/src/grpc/proto`.
- For unsupported languages: call REST directly or generate a client from OpenAPI/protobuf.

| Language | Package / install |
|---|---|
| Python | `pip install qdrant-client` (or `qdrant-client[fastembed]` for local embeddings) |
| JavaScript/TypeScript | `npm install @qdrant/js-client-rest` |
| Rust | `cargo add qdrant-client` |
| Go | `go get github.com/qdrant/go-client` |
| .NET/C# | `dotnet add package Qdrant.Client` |
| Java | `io.qdrant:client` via Maven Central |

## GitHub repo (github.com/qdrant/qdrant)

- ~33.9k stars, ~2.6k forks. Latest release: **v1.19.0** (published 2026-08-05; adds TurboQuant 4-bit quantization, unified memory usage strategies, prefix matching in filters).
- Minimal demo command in README: `docker run -p 6333:6333 qdrant/qdrant`.
- Notable directories: `/src` (server source), `/lib` (core library crates, incl. `lib/api` with gRPC protos), `/tests`, `/docs`, `/config` (default config files), `/openapi` (OpenAPI spec), `/tools`.
- Demo projects: semantic text search, similar image search (food discovery), extreme classification (e-commerce categorization).
- Official SDKs: Python, JS/TS, Rust, Go, .NET/C#, Java.

## FAQ — Qdrant fundamentals (key numbers & gotchas)

- **Max dense vector dimension: 65,535.**
- No payload size limit built in (configurable upper limits available); no hard limit on vectors per point (any mix of dense/sparse/multivectors, RAM-bound).
- Points with **zero vectors** are allowed — reachable via scroll/filter, invisible to NN search.
- **Collections**: no strict count limit, but many small collections is an antipattern (one-collection-per-user/dialog/document is explicitly discouraged — use multitenancy/payload partitioning instead).
- **Create payload indexes before uploading data**; adding one later forces a full HNSW reindex.
- **Upgrades**: only consecutive minor versions guaranteed compatible (1.1 → 1.2 → 1.3); client must be within one minor version of the server; **downgrades unsupported** (storage migrations irreversible).
- Search internals: default `hnsw_ef` = `ef_construct` (100); Qdrant sets `ef = max(ef, limit)` automatically.
- Batch upload: no universal optimum; start with **64–256 points/batch** and benchmark.
- Upsert of an identical point still does delete-mark + re-insert (no dedup check). Deletes are soft (bitmask); physical cleanup is async via the Vacuum Optimizer.
- Point `version` field = internal shard-level operation number, not an application-level write counter.
- **Quantization**: original full-precision vectors must be kept (needed for reindex/rescore). Rescoring on by default for binary quantization and TurboQuant 1/1.5/2-bit.
- Security: read-only API keys supported; JWT-based granular keys can scope read/write to individual collections.
- Scaling: vertical + horizontal scale-down possible on Cloud; disk size cannot shrink on vertical scale-down. CPU is the primary compute path; GPU indexing supported across major vendors.


---

# Part 2 — Data Management: Collections, Points, Vectors, Payload, Indexing, Quantization

Sources: qdrant.tech/documentation/manage-data/{collections,points,vectors,payload,indexing,storage,quantization,multitenancy,bulk-upload}/, /documentation/ops-optimization/optimizer/, /articles/bulk-uploads-in-qdrant/. Current as of Qdrant ~v1.19 (2026-08).

---

## 2.1 Collections

A collection is a named set of points. All vectors under one (named) vector space share dimensionality and distance metric. Distance metrics: `Dot`, `Cosine` (implemented as normalized dot product), `Euclid`, `Manhattan`.

**Create (REST):**
```http
PUT /collections/{collection_name}
{ "vectors": { "size": 300, "distance": "Cosine" } }
```

**Create (Python):**
```python
from qdrant_client import QdrantClient, models
client = QdrantClient(url="http://localhost:6333")
client.create_collection(
    collection_name="my_collection",
    vectors_config=models.VectorParams(size=100, distance=models.Distance.COSINE),
)
```

**Multiple named vectors per collection** (v0.10+) — different sizes/metrics per name:
```http
PUT /collections/{collection_name}
{ "vectors": {
    "image": {"size": 4, "distance": "Dot"},
    "text":  {"size": 8, "distance": "Cosine"} } }
```
```python
client.create_collection(
    collection_name="c",
    vectors_config={
        "image": models.VectorParams(size=4, distance=models.Distance.DOT),
        "text": models.VectorParams(size=8, distance=models.Distance.COSINE),
    },
)
```

**Sparse vectors config** (v1.7+) — always named; names must not collide with dense names; distance is always Dot (implicit):
```python
client.create_collection(
    collection_name="c",
    vectors_config={},                        # can be empty
    sparse_vectors_config={"text": models.SparseVectorParams()},
)
```

**Other collection ops:**
```http
GET    /collections                       # list
GET    /collections/{name}                # info (status, counts, config)
GET    /collections/{name}/exists         # v1.8+
DELETE /collections/{name}
GET    /aliases
```

**Update collection** — updatable: `optimizers_config`, `hnsw_config`, `quantization_config`, per-vector `vectors_config` (hnsw/quantization/memory), `params` (write_consistency_factor, payload memory tier), `strict_mode_config`:
```python
client.update_collection(
    collection_name="c",
    optimizers_config=models.OptimizersConfigDiff(indexing_threshold=10000),
)
```

**Add/remove named vectors on an existing collection** (v1.18+):
```http
PUT /collections/{name}/vectors/{vector_name}
{ "dense": { "size": 256, "distance": "Cosine" } }

PUT /collections/{name}/vectors/{vector_name}
{ "sparse": { "modifier": "Idf" } }

DELETE /collections/{name}/vectors/{vector_name}
```
```python
client.create_vector_name(
    collection_name="c", vector_name="v",
    vector_name_config=models.DenseVectorNameConfig(
        dense=models.DenseVectorConfig(size=256, distance=models.Distance.COSINE)),
)
```

**Aliases** (atomic switch enables zero-downtime reindex):
```http
POST /collections/aliases
{ "actions": [
    {"delete_alias": {"alias_name": "production_collection"}},
    {"create_alias": {"collection_name": "example_collection",
                      "alias_name": "production_collection"}} ] }
```

**Collection metadata** (v1.16+): `metadata={...}` on `create_collection` / `update_collection` — arbitrary JSON for bookkeeping.

**Key create-time config params:** `shard_number`, `replication_factor`, `write_consistency_factor`, `on_disk_payload` (bool), `wal_config`, `hnsw_config` (m, ef_construct, full_scan_threshold, payload_m, on_disk/memory), `quantization_config`, `optimizers_config`, `strict_mode_config`, per-vector `datatype` and `on_disk`/`memory`.

---

## 2.2 Points

**IDs:** 64-bit unsigned int OR UUID string (simple `936DA01F9ABD4d9d80C702AF85C822A8`, hyphenated `550e8400-e29b-41d4-a716-446655440000`, or URN). Mixing formats in one request is allowed.

**Upsert — record-oriented:**
```http
PUT /collections/{name}/points?wait=true
{ "points": [ {"id": 1, "vector": [0.9,0.1,0.1], "payload": {"color":"red"}} ] }
```
```python
client.upsert(
    collection_name="c",
    points=[models.PointStruct(id=1, vector=[0.9,0.1,0.1], payload={"color":"red"})],
)
```

**Upsert — column-oriented batch** (equivalent, convenience form):
```python
client.upsert(
    collection_name="c",
    points=models.Batch(
        ids=[1, 2, 3],
        payloads=[{"color":"red"}, {"color":"green"}, {"color":"blue"}],
        vectors=[[0.9,0.1,0.1],[0.1,0.9,0.1],[0.1,0.1,0.9]],
    ),
)
```

**Update modes** (v1.17+), mutually exclusive: `upsert` (default: insert-or-update), `insert_only` (skip existing IDs), `update_only` (skip missing IDs). Python: `update_mode=models.UpdateMode.INSERT_ONLY`.

**Conditional updates** (v1.16+): `update_filter=models.Filter(must=[models.FieldCondition(key="version", match=models.MatchValue(value=2))])` — precondition on existing point. Note: on a non-existent point a conditional update behaves as a regular upsert unless combined with `update_mode="update_only"`.

**Retrieve by IDs:**
```python
client.retrieve(collection_name="c", ids=[0, 3, 100],
                with_payload=True, with_vectors=False)
```

**Scroll (paginate/filter):** response carries `next_page_offset` (null = last page).
```python
client.scroll(
    collection_name="c",
    scroll_filter=models.Filter(must=[
        models.FieldCondition(key="color", match=models.MatchValue(value="red"))]),
    limit=10, with_payload=True, with_vectors=False,
)
# order_by (v1.8+, needs range-capable payload index):
client.scroll(collection_name="c", limit=15,
    order_by=models.OrderBy(key="timestamp", direction=models.Direction.DESC, start_from=123))
```

**Delete points** — by IDs or by filter:
```python
client.delete(collection_name="c",
    points_selector=models.PointIdsList(points=[0, 3, 100]))
client.delete(collection_name="c",
    points_selector=models.FilterSelector(filter=models.Filter(must=[
        models.FieldCondition(key="color", match=models.MatchValue(value="red"))])))
```

**Update vectors only** (v1.2+) — keeps payload and other named vectors:
```python
client.update_vectors(collection_name="c",
    points=[models.PointVectors(id=1, vector={"image": [0.1,0.2,0.3,0.4]})])
```

**Delete named vectors from points** (v1.2+):
```python
client.delete_vectors(collection_name="c", points=[0,3,100], vectors=["text","image"])
```

**Batch update ops** (v1.5+) — sequential mixed operations in one call. Supported: upsert, delete_points, update_vectors, delete_vectors, set_payload, overwrite_payload, delete_payload, clear_payload:
```python
client.batch_update_points(collection_name="c", update_operations=[
    models.UpsertOperation(upsert=models.PointsList(points=[...])),
    models.DeleteOperation(...),
])
```

**`wait` parameter:** `wait=false` (default) returns `"status": "acknowledged"` immediately (async apply); `wait=true` blocks until applied (`"status": "completed"`). For bulk insertion use async requests to exploit pipelining.

**Guarantees:** writes go WAL-first (durable once acknowledged, survives power loss), then apply to segments. All APIs are idempotent — repeating the same call equals one execution.

---

## 2.3 Vectors

**Dense:** fixed-length float arrays (`[-0.013, 0.020, ...]`).

**Sparse** (v1.7+): index/value pairs, dynamic length, indices in u32 range; arrays must be equal length, indices unique.
```json
{ "indices": [1, 3, 5, 7], "values": [0.1, 0.2, 0.3, 0.4] }
```
```python
# upsert
models.PointStruct(id=1, vector={"text": models.SparseVector(indices=[1,3,5,7], values=[0.1,0.2,0.3,0.4])})
# query
client.query_points(collection_name="c",
    query=models.SparseVector(indices=[1,3,5,7], values=[0.1,0.2,0.3,0.4]),
    using="text")
```
Optional `modifier=models.Modifier.IDF` on `SparseVectorParams` for BM25/IDF weighting. Note: IDF statistics are collection-global, not per tenant — use the `idf` query param to scope.

**Multivectors / late interaction (ColBERT-style):** each point stores a variable-size matrix of same-width vectors; scored with MaxSim (single combined score per point):
score = Σ_i max_j Sim(A_i, B_j)
```python
client.create_collection(collection_name="c",
    vectors_config=models.VectorParams(
        size=128, distance=models.Distance.COSINE,
        multivector_config=models.MultiVectorConfig(
            comparator=models.MultiVectorComparator.MAX_SIM)))
# upsert / query take a list of vectors:
models.PointStruct(id=1, vector=[[...128 floats...], [...], [...]])
```

**Named vectors** — mix dense + sparse per point; query selects space via `using="image"`:
```python
models.PointStruct(id=1, vector={
    "image": [0.9, 0.1, 0.1, 0.2],
    "text": [0.4, 0.7, 0.1, 0.8, 0.1],
    "text-sparse": {"indices": [1,3,5,7], "values": [0.1,0.2,0.3,0.4]},
})
```

**Datatypes** (`datatype` in VectorParams; also on `SparseIndexParams(datatype=...)`):
| Datatype | Size/dim | Notes |
|---|---|---|
| `float32` | 4 B | default (1536-dim ≈ 6 KB/vector) |
| `float16` | 2 B | half RAM, "virtually no impact" on quality |
| `uint8` | 1 B | values must fit 0–255 (sparse quantized in-flight) |
| `turbo4` (v1.19+) | 0.5 B | 4-bit TurboQuant; ~1/8 size; dense only |
```python
models.VectorParams(size=1024, distance=models.Distance.COSINE,
                    datatype=models.Datatype.UINT8)
```

**Server-side inference:** pass `models.Document(text=..., model="Qdrant/bm25")` as a vector value in upsert/query and Qdrant embeds it.

---

## 2.4 Payload

**Types** (all accept single value or array; array filter matches if any element matches): `keyword` (string), `integer` (i64), `float` (f64), `bool`, `geo` (`{"lon": ..., "lat": ...}`), `datetime` (RFC 3339, v1.8+), `uuid` (v1.11+, stored numerically).

**Set payload** — merge: updates given keys, preserves others. Supports nested targets via `key` path param (v1.8+):
```http
POST /collections/{name}/points/payload
{ "payload": {"property1": "string"}, "points": [0, 3, 10] }
```
```python
client.set_payload(collection_name="c", payload={"property1": "string"},
                   points=[0, 3, 10])           # also accepts key="nested.path"
```

**Overwrite payload** — full replacement of the payload object:
```python
client.overwrite_payload(collection_name="c", payload={"property1": "string"},
                         points=[0, 3, 10])
```

**Delete specific keys / clear all:**
```python
client.delete_payload(collection_name="c", keys=["color","price"], points=[0,3,100])
client.clear_payload(collection_name="c", points_selector=[0, 3, 100])
```
All payload ops also accept a filter selector instead of an ID list.

**Facet counts** (v1.12+, needs MatchValue-capable index on the field):
```python
client.facet(collection_name="c", key="size",
             facet_filter=models.Filter(must=[...]), exact=True)
```

---

## 2.5 Indexing

### Payload indexes
Create before ingesting data for best filterable-HNSW performance. Strict mode option `unindexed_filtering_retrieve=false` blocks filters on unindexed fields.

```http
PUT /collections/{name}/index
{ "field_name": "city", "field_schema": "keyword" }
```
```python
client.create_payload_index(collection_name="c", field_name="city",
    field_schema=models.PayloadSchemaType.KEYWORD)
```

Schema capabilities: `keyword` (match; optional `prefix=True` v1.19+), `integer` (match+range, tunable), `float` (range), `bool` (v1.4+), `geo` (bounding box / radius), `datetime` (range, v1.8+), `uuid` (v1.11+), `text` (full-text).

**Parameterized integer index** (v1.8+) — trim memory by disabling unused capability:
```python
field_schema=models.IntegerIndexParams(
    type=models.IntegerIndexType.INTEGER,
    lookup=False,   # disable Match
    range=True,     # keep Range
)
```

**Full-text index:**
```python
field_schema=models.TextIndexParams(
    type=models.TextIndexType.TEXT,
    tokenizer=models.TokenizerType.WORD,   # word | whitespace | prefix | multilingual
    min_token_len=2, max_token_len=10,
    lowercase=True,          # default True
    ascii_folding=False,     # default False (é→e)
    phrase_matching=False,   # default False; True enables quoted-phrase search
    stemmer=models.SnowballParams(type=models.Snowball.SNOWBALL,
                                  language=models.SnowballLanguage.ENGLISH),
    stopwords=models.StopwordsSet(languages=[models.Language.ENGLISH], custom=["example"]),
)
```

**Index placement / special flags** (v1.11+): `memory=models.Memory.PINNED` (default, RAM) | `CACHED` | `COLD` (disk); `is_tenant=True` (keyword/uuid only — see 2.8); `is_principal=True` (integer/float/datetime — optimizes storage around a primary filter field like timestamp); `enable_hnsw=False` (v1.17+, skip filter-aware HNSW edges for fields never combined with vector search).

### Vector index (HNSW)
Config defaults (overridable per collection or per named vector via `hnsw_config`):
```yaml
storage:
  hnsw_index:
    m: 16                         # edges per node; 0 disables global graph
    ef_construct: 100             # build-time candidate list size
    full_scan_threshold: 10000    # KB; below this, full scan instead of index
```
`payload_m`: per-tenant/filtered graph edges (used with `m=0` for tenant-only graphs). To force an HNSW rebuild after adding a payload index, bump `ef_construct` by 1.

### Sparse index
```python
sparse_vectors_config={"text": models.SparseVectorParams(
    index=models.SparseIndexParams(memory=models.Memory.PINNED,  # or CACHED/COLD
                                   datatype=models.Datatype.FLOAT16),
    modifier=models.Modifier.IDF)}
```
Dot-product only; sizes itself to observed dimensionality.

---

## 2.6 Storage, Segments, WAL, Optimizer

**Architecture:** collection data is split into segments, each with its own vector storage, payload storage, and indexes. Segments are appendable (insert/update/delete) or non-appendable (read/delete only); at least one appendable segment always exists.

**Writes are 2-stage:** (1) WAL append — ordered, sequence-numbered, durable; (2) apply to segments (versioned per point so out-of-order replays are ignored on recovery).

**Vector storage tiers** (Qdrant always memmaps files; tier controls pre-loading — newer `memory` API supersedes old `on_disk: true`):
- `cached` (default): pre-loaded into page cache at startup — fast first request.
- `cold`: no pre-load — reads hit disk first; use for large collections / low RAM (needs SSD/NVMe).
```python
models.VectorParams(size=768, distance=models.Distance.COSINE, memory=models.Memory.COLD)
# HNSW graph tier is separate:
hnsw_config=models.HnswConfigDiff(memory=models.Memory.COLD)
```
Legacy equivalent: `on_disk: true` in VectorParams; `on_disk_payload: true` at collection level.

**Payload storage:** tiers `cached` / `cold` (default; Gridstore, no pre-warm). Indexed payload fields stay in RAM regardless. Set via `payload.memory`.

**Optimizers** (`optimizers_config`, all changeable via `update_collection`):
| Param | Default | Meaning |
|---|---|---|
| `deleted_threshold` | 0.2 | vacuum when ≥20% of a segment's vectors are deleted |
| `vacuum_min_vector_number` | 1000 | min segment size to vacuum |
| `default_segment_number` | 0 (auto = CPU-based) | target segment count (merge optimizer) |
| `max_segment_size` (KB) | null (auto) | cap on merged segment size |
| `memmap_threshold` (KB) | 200000 (0 = off) | segments above this use read-only memmap |
| `indexing_threshold` (KB) | 10000 | segments above this get HNSW built; **0 disables indexing** |
| `flush_interval_sec` | 5 | WAL flush cadence |
| `max_optimization_threads` | auto | concurrent optimization jobs |

WAL config: `wal_config: { wal_capacity_mb, wal_segments_ahead }`.
Guideline: keep `memmap_threshold` == `indexing_threshold` normally; lower memmap_threshold (e.g. 5000) for write-heavy/low-RAM setups. Monitor: `GET /collections/{name}/optimizations?with=queued,completed,idle_segments`. Experimental v1.17.1+: `prevent_unoptimized` — writes to unindexed segments are stored but hidden from search until indexed (requires `wait=false` writes).

---

## 2.7 Quantization

Configured via `quantization_config` at create/update; originals are always kept (rescoring possible).

| Method | Compression | Trade-off |
|---|---|---|
| Scalar (int8) | 4x | <1% avg error; safest default |
| TurboQuant (v1.18+) | 8x–32x (`bits4`/`bits2`/`bits1_5`/`bits1`) | strong recall across models; SIMD for Cosine/Dot/L2 (not Manhattan) |
| Binary | 16x–32x (`one_bit` default, `one_and_half_bits`, `two_bits`) | fastest; needs centered distributions; tested: OpenAI ada-002 0.98 recall@100 @ 4x oversampling, Cohere 4096d 0.98 recall@50 @ 2x oversampling |
| Product | x4–x64 (`x4|x8|x16|x32|x64`) | max compression; not SIMD-friendly, slowest — only when footprint is top priority |

```python
# Scalar
quantization_config=models.ScalarQuantization(
    scalar=models.ScalarQuantizationConfig(
        type=models.ScalarType.INT8,
        quantile=0.99,                 # default 0.99: clip 1% outliers
        memory=models.Memory.PINNED))  # PINNED (RAM) or COLD (disk)
# Binary
quantization_config=models.BinaryQuantization(
    binary=models.BinaryQuantizationConfig(
        encoding=models.BinaryQuantizationEncoding.TWO_BITS,
        memory=models.Memory.PINNED))
# also: query_encoding=models.BinaryQuantizationQueryEncoding.SCALAR8BITS  (asymmetric)
# Product
quantization_config=models.ProductQuantization(
    product=models.ProductQuantizationConfig(
        compression=models.CompressionRatio.X16, memory=models.Memory.PINNED))
# TurboQuant
quantization_config=models.TurboQuantization(
    turbo=models.TurboQuantQuantizationConfig(
        bits=models.TurboQuantBitSize.BITS2, memory=models.Memory.PINNED))
```

**Query-time controls:**
```python
search_params=models.SearchParams(quantization=models.QuantizationSearchParams(
    ignore=False,       # True = search originals, skip quantized
    rescore=True,       # re-rank top-k with original vectors (default on for binary & TurboQuant <4-bit)
    oversampling=2.0,   # fetch limit*2 candidates before rescore
))
```

**Deployment patterns:** (1) originals cached + quantized pinned = fastest, most RAM; (2) originals cold + quantized pinned = balanced (consider `rescore=False` if disk-bound); (3) all cold = smallest RAM, needs NVMe. JSON REST shape mirrors Python, e.g. `"quantization_config": {"scalar": {"type": "int8", "quantile": 0.99, "always_ram": true}}` (older `always_ram: true` == `memory: pinned`).

---

## 2.8 Multitenancy

**Default choice: one collection, payload-partitioned.** Per-tenant collections carry per-collection overhead (Qdrant Cloud caps ~1000 collections/cluster); use collection-per-tenant only for few, large, strict-isolation tenants.

**Pattern:** every point carries a tenant key; every query filters on it.
```python
# 1. tenant index — co-locates a tenant's vectors on disk (sequential reads):
client.create_payload_index(collection_name="c", field_name="group_id",
    field_schema=models.KeywordIndexParams(
        type=models.KeywordIndexType.KEYWORD, is_tenant=True))   # v1.11+; keyword|uuid
# 2. upsert with tenant payload:
models.PointStruct(id=1, vector=[0.9,0.1,0.1], payload={"group_id": "user_1"})
# 3. always filter:
client.query_points(collection_name="c", query=[0.1,0.1,0.9],
    query_filter=models.Filter(must=[models.FieldCondition(
        key="group_id", match=models.MatchValue(value="user_1"))]),
    limit=10)
```
```http
PUT /collections/{name}/index
{ "field_name": "group_id", "field_schema": {"type": "keyword", "is_tenant": true} }
```

**Per-tenant HNSW** — skip the global graph, build per-group graphs (faster ingest, fast filtered search):
```python
client.create_collection(collection_name="c",
    vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE),
    hnsw_config=models.HnswConfigDiff(payload_m=16, m=0))
```

**Custom sharding** for hard isolation of big tenants:
```python
client.create_collection(collection_name="c", shard_number=1,
                         sharding_method=models.ShardingMethod.CUSTOM)
client.create_shard_key("c", "user_1")
client.upsert(collection_name="c", points=[...], shard_key_selector="user_1")
```

Caveats: global (unfiltered) queries scan all groups (slow); sparse-vector IDF stats are not tenant-isolated (scope via `idf` param).

---

## 2.9 Bulk Upload Best Practices

1. **Batch size 64–256 points** per request — smaller wastes network, larger raises server memory + retry cost.
2. **Parallelize: 2–4 concurrent upload threads** (roughly one per shard); a single thread rarely saturates the server.
3. **`wait=false`** (default) on upserts for pipelining; check collection status afterwards.
4. **Create payload indexes BEFORE uploading** — one-pass filterable HNSW build instead of a rebuild.
5. **Shard for write parallelism:** `shard_number=2..4` per machine at creation.
6. **Go cold/on-disk for RAM-constrained loads:** `memory=models.Memory.COLD` (or `on_disk=True`) in VectorParams; combine with quantization pinned in RAM.
7. **Defer HNSW during ingest, then re-enable** — set `indexing_threshold=0` (or `m=0`) at creation so no graph is built while uploading, then restore:
```python
client.create_collection(collection_name="c",
    vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE),
    optimizers_config=models.OptimizersConfigDiff(indexing_threshold=0))
# ... bulk upload ...
client.update_collection(collection_name="c",
    optimizers_config=models.OptimizersConfigDiff(indexing_threshold=20000))
```
8. **Python helper** — auto-batching + parallelism:
```python
client.upload_points(collection_name="c", points=points, batch_size=256, parallel=4)
```
There is no universal best config — tune batch/parallel/shards against your workload.


---

# Part 3 — Search: Query API, Filtering, Hybrid, Explore

Sources: qdrant.tech/documentation/search/{search,filtering,hybrid-queries,explore,search-relevance,low-latency-search}, /search/text-search/{full-text-search,text-filtering}, /guides/quantization. All queries go through the universal Query API: `POST /collections/{collection}/points/query` (batch: `/points/query/batch`, groups: `/points/query/groups`). Python: `client.query_points(...)`, `client.query_batch_points(...)`, `client.query_points_groups(...)`.

## 3.1 Query API — query_points

### Common parameters (apply to every query type)

| Param | Type | Default | Notes |
|---|---|---|---|
| `query` | dense vector / sparse vector / point ID / query object | required | vector = nearest search; ID = "more like this point"; objects: `recommend`, `discover`, `context`, `fusion`/`rrf`, `formula`, `sample`, `nearest`+`mmr`, `relevance_feedback` |
| `limit` | int | 10 | max results |
| `offset` | int | 0 | skip N results; in hybrid queries offset applies ONLY to the main query, not prefetches |
| `filter` | Filter | null | payload conditions (Python kwarg: `query_filter`) |
| `score_threshold` | float | null | exclude results below (or above, for Euclid) threshold |
| `with_payload` | bool / array / object | false in raw REST (client returns payload by default) | `true`, list of keys, or `{"include":[...]}` / `{"exclude":[...]}` |
| `with_vectors` | bool / array | false | |
| `using` | string | default unnamed vector | named vector to search against |
| `params` | SearchParams | null | see 3.7 |
| `lookup_from` | `{collection, vector}` | null | resolve query IDs from another collection |
| `shard_key`, `consistency`, `timeout` | — | null | routing/consistency/seconds |

### Nearest search — REST

```json
POST /collections/{collection_name}/points/query
{
  "query": [0.2, 0.1, 0.9, 0.7],
  "limit": 3,
  "offset": 0,
  "filter": { "must": [ { "key": "city", "match": { "value": "London" } } ] },
  "params": { "hnsw_ef": 128, "exact": false, "indexed_only": false },
  "score_threshold": 0.5,
  "with_payload": true,
  "with_vectors": false,
  "using": "dense"
}
```

### Nearest search — Python

```python
from qdrant_client import QdrantClient, models
client = QdrantClient(url="http://localhost:6333")

client.query_points(
    collection_name="collection_name",
    query=[0.2, 0.1, 0.9, 0.7],
    limit=3,
    offset=0,
    query_filter=models.Filter(must=[models.FieldCondition(
        key="city", match=models.MatchValue(value="London"))]),
    search_params=models.SearchParams(hnsw_ef=128, exact=False),
    score_threshold=0.5,
    with_payload=True,
    with_vectors=False,
    using="dense",
)
```

Response items: `{"id": ..., "score": 0.81, "payload": {...}, "vector": [...]}` wrapped in `{"result": {"points": [...]}, "status": "ok", "time": ...}`.

### Search by point ID (uses that point's stored vector; the point itself is excluded)

```json
{ "query": "43cf51e2-8777-4f52-bc74-c2cbde0c8b04", "using": "dense",
  "lookup_from": { "collection": "other_collection", "vector": "dense" }, "limit": 3 }
```
```python
client.query_points(
    collection_name="collection_name",
    query="43cf51e2-8777-4f52-bc74-c2cbde0c8b04",   # or int ID
    using="dense",
    lookup_from=models.LookupLocation(collection="other_collection", vector="dense"),
    limit=3,
)
```

### Sparse vector search

```json
{ "query": { "indices": [1, 3, 5, 7], "values": [0.1, 0.2, 0.3, 0.4] }, "using": "text", "limit": 3 }
```
```python
client.query_points(
    collection_name="collection_name",
    query=models.SparseVector(indices=[1, 3, 5, 7], values=[0.1, 0.2, 0.3, 0.4]),
    using="text",
)
```

### Batch search — `POST /collections/{name}/points/query/batch`

```json
{ "searches": [
    { "query": [0.2, 0.1, 0.9, 0.7], "filter": {}, "limit": 3, "offset": 0, "with_payload": true },
    { "query": [0.5, 0.3, 0.2, 0.3], "limit": 3 }
] }
```
```python
client.query_batch_points(
    collection_name="collection_name",
    requests=[
        models.QueryRequest(query=[0.2, 0.1, 0.9, 0.7], limit=3, with_payload=True),
        models.QueryRequest(query=[0.5, 0.3, 0.2, 0.3], limit=3),
    ],
)
```
Note: inside `QueryRequest` the filter kwarg is `filter=` (not `query_filter=`). Result is a list of result lists, same order as requests. Batch is also the idiom for progressive filter relaxation (strict filter → looser filter → no filter in one round trip).

### Grouping — `POST /collections/{name}/points/query/groups`

`limit` = max groups, `group_size` = points per group (default 1). `with_lookup` joins a record from another collection per group.

```json
{
  "query": [1.1], "group_by": "document_id", "limit": 4, "group_size": 2,
  "with_lookup": { "collection": "documents", "with_payload": ["title", "text"], "with_vectors": false }
}
```
```python
client.query_points_groups(
    collection_name="collection_name",
    query=[1.1],
    group_by="document_id",       # payload field path; keyword or number values
    limit=4,
    group_size=2,
    with_lookup=models.WithLookup(
        collection="documents", with_payload=["title", "text"], with_vectors=False),
)
```

### Random sampling

```json
{ "query": { "sample": "random" }, "limit": 10 }
```
```python
client.query_points(
    collection_name="collection_name",
    query=models.SampleQuery(sample=models.Sample.RANDOM),
    limit=10,
)
```

## 3.2 Filtering

Filter object clauses — combinable and recursively nestable:
- `must`: all conditions true (AND)
- `should`: at least one true (OR)
- `must_not`: none true (AND NOT)
- `min_should`: `{"min_should": {"conditions": [...], "min_count": n}}` — at least n true

```json
{ "filter": {
    "must":     [ { "key": "city",  "match": { "value": "London" } } ],
    "must_not": [ { "key": "color", "match": { "value": "red" } } ]
} }
```
```python
models.Filter(
    must=[models.FieldCondition(key="city", match=models.MatchValue(value="London"))],
    must_not=[models.FieldCondition(key="color", match=models.MatchValue(value="red"))],
)
```

### Condition types

| Condition | JSON | Python |
|---|---|---|
| Match (exact; keyword/int/bool/UUID) | `{"key":"color","match":{"value":"red"}}` | `models.FieldCondition(key="color", match=models.MatchValue(value="red"))` |
| Match Any (IN) | `{"key":"color","match":{"any":["black","yellow"]}}` | `match=models.MatchAny(any=["black","yellow"])` |
| Match Except (NOT IN) | `{"key":"color","match":{"except":["black","yellow"]}}` | `match=models.MatchExcept(**{"except": ["black","yellow"]})` |
| Prefix match | `{"key":"url","match":{"prefix":"https://qdrant."}}` | `match=models.MatchPrefix(prefix="https://qdrant.")` |
| Full-text (ALL terms, needs text index) | `{"key":"description","match":{"text":"good cheap"}}` | `match=models.MatchText(text="good cheap")` |
| Full-text any (ANY term) | `{"key":"description","match":{"text_any":"good cheap"}}` | `match=models.MatchTextAny(text_any="good cheap")` |
| Phrase (exact sequence; needs `phrase_matching: true` on index) | `{"key":"description","match":{"phrase":"brown fox"}}` | `match=models.MatchPhrase(phrase="brown fox")` |
| Range (numbers) | `{"key":"price","range":{"gt":null,"gte":100.0,"lt":null,"lte":450.0}}` | `range=models.Range(gte=100.0, lte=450.0)` |
| Datetime range (RFC 3339) | `{"key":"date","range":{"gt":"2023-02-08T10:49:00Z","lte":"2024-01-31T10:14:31Z"}}` | `range=models.DatetimeRange(gt="2023-02-08T10:49:00Z", lte="2024-01-31T10:14:31Z")` |
| Geo bounding box | `{"key":"location","geo_bounding_box":{"top_left":{"lon":13.403683,"lat":52.520711},"bottom_right":{"lon":13.455868,"lat":52.495862}}}` | `geo_bounding_box=models.GeoBoundingBox(top_left=models.GeoPoint(lon=..., lat=...), bottom_right=models.GeoPoint(...))` |
| Geo radius (meters) | `{"key":"location","geo_radius":{"center":{"lon":13.403683,"lat":52.520711},"radius":1000.0}}` | `geo_radius=models.GeoRadius(center=models.GeoPoint(...), radius=1000.0)` |
| Geo polygon (exterior ring + optional interior holes; first point == last point) | `{"key":"location","geo_polygon":{"exterior":{"points":[...]},"interiors":[{"points":[...]}]}}` | `geo_polygon=models.GeoPolygon(exterior=models.GeoLineString(points=[models.GeoPoint(...), ...]), interiors=[...])` |
| Values count | `{"key":"comments","values_count":{"gt":2}}` (gt/gte/lt/lte) | `values_count=models.ValuesCount(gt=2)` |
| Is Empty (missing, null, or []) | `{"is_empty":{"key":"reports"}}` | `models.IsEmptyCondition(is_empty=models.PayloadField(key="reports"))` |
| Is Null | `{"is_null":{"key":"reports"}}` | `models.IsNullCondition(is_null=models.PayloadField(key="reports"))` |
| Has ID | `{"has_id":[1,3,5,7,9,11]}` | `models.HasIdCondition(has_id=[1,3,5,7,9,11])` |
| Has vector (named vector present) | `{"has_vector":"image"}` | `models.HasVectorCondition(has_vector="image")` |
| Slice (deterministic disjoint subsets) | `{"slice":{"index":3,"total":8}}` | `models.SliceCondition(slice=models.Slice(index=3, total=8))` |

Nested access: dot notation `country.name`; array projection `country.cities[].population`. To constrain conditions to the SAME array element, use a nested filter:

```json
{ "filter": { "must": [ { "nested": { "key": "diet", "filter": { "must": [
  { "key": "food", "match": { "value": "meat" } },
  { "key": "likes", "match": { "value": true } }
] } } } ] } }
```
```python
models.Filter(must=[models.NestedCondition(nested=models.Nested(
    key="diet",
    filter=models.Filter(must=[
        models.FieldCondition(key="food", match=models.MatchValue(value="meat")),
        models.FieldCondition(key="likes", match=models.MatchValue(value=True)),
    ]),
))])
```

Combine with any search by passing the filter in the same request (`filter` in REST, `query_filter=` in `query_points`). Qdrant does filterable-HNSW in-search filtering, not post-filtering. Create payload indexes for every filtered field, ideally before ingesting data; strict mode (default on Qdrant Cloud) rejects filters on unindexed fields.

## 3.3 Hybrid and multi-stage queries (prefetch)

If a query has ≥1 `prefetch`, Qdrant runs the prefetch(es) first, then applies the main `query` over their combined results. Prefetches nest recursively. Each `Prefetch` accepts its own `query`, `using`, `filter`, `limit`, `params`, `score_threshold`, and nested `prefetch`. Prefetch `limit` must be ≥ main `limit + offset` (offset applies only to the main query).

### Fusion — RRF (rank-based; score(d) = Σ 1/(k + rank), zero-based ranks, k default 2)

```json
POST /collections/{collection_name}/points/query
{
  "prefetch": [
    { "query": { "indices": [1, 42], "values": [0.22, 0.8] }, "using": "sparse", "limit": 20 },
    { "query": [0.01, 0.45, 0.67], "using": "dense", "limit": 20 }
  ],
  "query": { "rrf": {} },
  "limit": 10
}
```
```python
client.query_points(
    collection_name="{collection_name}",
    prefetch=[
        models.Prefetch(query=models.SparseVector(indices=[1, 42], values=[0.22, 0.8]),
                        using="sparse", limit=20),
        models.Prefetch(query=[0.01, 0.45, 0.67], using="dense", limit=20),
    ],
    query=models.RrfQuery(rrf=models.Rrf()),         # custom k: models.Rrf(k=60)
)
```
Weighted RRF (v1.17+): `models.RrfQuery(rrf=models.Rrf(weights=[3.0, 1.0]))` — one weight per prefetch, in order; tune on an eval split, else keep defaults. Legacy JSON form `{"fusion": "rrf"}` / `models.FusionQuery(fusion=models.Fusion.RRF)` also valid.

### Fusion — DBSF (distribution-based score fusion: normalize each result set by ŝ = (s − (μ−3σ)) / 6σ, per-query, stateless; not clipped to [0,1]; emits 0.5 when degenerate)

```json
{ "prefetch": [ ...same as above... ], "query": { "fusion": "dbsf" }, "limit": 10 }
```
```python
query=models.FusionQuery(fusion=models.Fusion.DBSF)
```
Choosing: RRF = safe default (rank-based, scale-free); DBSF when raw scores are well-calibrated; weighted RRF when you can tune. Never linearly blend raw dense+sparse scores without normalization. In distributed collections, fusion must be the top-level `query` (fusion inside a prefetch fuses per-shard only).

### Multi-stage rescoring (cheap retrieve → expensive rerank)

```python
# MRL byte vector -> full vector
client.query_points(
    collection_name="{collection_name}",
    prefetch=models.Prefetch(query=[1, 23, 45, 67], using="mrl_byte", limit=1000),
    query=[0.01, 0.299, 0.45, 0.67],
    using="full",
    limit=10,
)

# dense -> ColBERT multivector late-interaction rerank
client.query_points(
    collection_name="{collection_name}",
    prefetch=models.Prefetch(query=[0.01, 0.45, 0.67, 0.53], limit=100),
    query=[[0.1, 0.2, 0.32], [0.2, 0.1, 0.52], [0.8, 0.9, 0.93]],  # one vector per query token
    using="colbert",
    limit=10,
)

# three stages: byte -> full dense -> ColBERT
client.query_points(
    collection_name="{collection_name}",
    prefetch=models.Prefetch(
        prefetch=models.Prefetch(query=[1, 23, 45, 67], using="mrl_byte", limit=1000),
        query=[0.01, 0.45, 0.67],
        using="full",
        limit=100,
    ),
    query=[[0.17, 0.23, 0.52], [0.22, 0.11, 0.63], [0.86, 0.93, 0.12]],
    using="colbert",
    limit=10,
)
```
Tip: for vectors used only in rescoring (e.g. ColBERT multivectors), set `hnsw_config.m = 0` to skip building HNSW for them.

### Formula queries (score boosting; v1.14+, rescoring step only)

`query: {"formula": ...}` rescores prefetch results with a custom expression. Results always sorted descending (negate for Euclidean). Available expressions: constant, `"$score"` (also `"$score[0]"`, `"$score[1]"` per prefetch), payload key, condition (→ 1.0/0.0), `sum`, `mult`, `div`, `pow`, `sqrt`, `log10`, `ln`, `exp`, `abs`, `geo_distance` (haversine), `lin_decay`/`exp_decay`/`gauss_decay`, `datetime`, `datetime_key`. Missing variables default to 0.0 only if given in `defaults`; non-numeric payloads error; `0.0 * expr` is lazily skipped.

Tag boosting (condition weights):
```json
{
  "prefetch": { "query": [0.2, 0.8], "limit": 50 },
  "query": { "formula": { "sum": [
      "$score",
      { "mult": [0.5,  { "key": "tag", "match": { "any": ["h1", "h2", "h3", "h4"] } }] },
      { "mult": [0.25, { "key": "tag", "match": { "any": ["p", "li"] } }] }
  ] } }
}
```
```python
client.query_points(
    collection_name="{collection_name}",
    prefetch=models.Prefetch(query=[0.1, 0.45, 0.67], limit=50),
    query=models.FormulaQuery(formula=models.SumExpression(sum=[
        "$score",
        models.MultExpression(mult=[0.5, models.FieldCondition(
            key="tag", match=models.MatchAny(any=["h1", "h2", "h3", "h4"]))]),
        models.MultExpression(mult=[0.25, models.FieldCondition(
            key="tag", match=models.MatchAny(any=["p", "li"]))]),
    ])),
)
```

Decay functions — params: `x` (required), `target` (default 0.0 / now), `scale` (required, >0; distance at which output = midpoint), `midpoint` (default 0.5, exclusive (0,1)). `lin_decay` range [0,1]; `exp_decay`, `gauss_decay` (0,1].

Recency boost (RRF + exp_decay):
```python
client.query_points(
    collection_name="{collection_name}",
    prefetch=models.Prefetch(
        prefetch=[
            models.Prefetch(query=models.SparseVector(indices=[1, 42], values=[0.22, 0.8]),
                            using="sparse", limit=100),
            models.Prefetch(query=[0.01, 0.45, 0.67], using="dense", limit=100),
        ],
        query=models.RrfQuery(rrf=models.Rrf()),
        limit=100,
    ),
    query=models.FormulaQuery(formula=models.SumExpression(sum=[
        "$score",
        models.MultExpression(mult=[
            0.1,  # calibrate decay [0,1] against RRF score scale
            models.ExpDecayExpression(exp_decay=models.DecayParamsExpression(
                x=models.DatetimeKeyExpression(datetime_key="published_at"),
                target=models.DatetimeExpression(datetime="2024-01-01T00:00:00Z"),
                scale=86400 * 180,   # seconds
                midpoint=0.5,
            )),
        ]),
    ])),
    limit=10,
)
```

Geo proximity boost (with `defaults` for points missing the payload key):
```json
{ "query": { "formula": { "sum": [ "$score",
    { "gauss_decay": {
        "x": { "geo_distance": { "origin": { "lat": 52.504043, "lon": 13.393236 }, "to": "geo.location" } },
        "scale": 5000 } }
  ] },
  "defaults": { "geo.location": { "lat": 48.137154, "lon": 11.576124 } } } }
```

### Hybrid + grouping

```python
client.query_points_groups(
    collection_name="{collection_name}",
    prefetch=[
        models.Prefetch(query=models.SparseVector(indices=[1, 42], values=[0.22, 0.8]),
                        using="sparse", limit=100),
        models.Prefetch(query=[0.01, 0.45, 0.67], using="dense", limit=100),
    ],
    query=models.RrfQuery(rrf=models.Rrf()),
    group_by="document_id",
    limit=4,
    group_size=2,
)
```

## 3.4 Full-text search and text filtering

### Two string semantics
- **keyword** payload/index: exact, case-sensitive, not tokenized — categories, tags, IDs.
- **text** index: tokenized, case-insensitive by default — term filtering inside prose.

### Text index creation

```http
PUT /collections/books/index?wait=true
{ "field_name": "title",
  "field_schema": { "type": "text", "ascii_folding": true, "phrase_matching": true } }
```
```python
client.create_payload_index(
    collection_name="books",
    field_name="title",
    field_schema=models.TextIndexParams(
        type=models.TextIndexType.TEXT,
        tokenizer=models.TokenizerType.WORD,   # word (default) | whitespace | prefix | multilingual
        lowercase=True,                        # default True
        ascii_folding=True,                    # default False; "café" -> "cafe"
        phrase_matching=True,                  # default False; required for match.phrase
        # min_token_len=2, max_token_len=15,   # token length bounds
        # stemmer=models.SnowballParams(type=models.Snowball.SNOWBALL, language=models.SnowballLanguage.ENGLISH),
        # stopwords=models.Language.ENGLISH,   # or custom set
        # on_disk=True,
    ),
)
# keyword index: field_schema=models.PayloadSchemaType.KEYWORD
```
Processing pipeline: tokenize → lowercase → ascii_folding → stemming → stopword removal. Filter strings get the same processing at query time.

### Text filter semantics

| Method | Logic | Case-sensitive |
|---|---|---|
| `match.text` | ALL terms (AND) | no |
| `match.text_any` | ANY term (OR) | no |
| `match.phrase` | exact ordered sequence | no |
| `match.value` on keyword | exact whole string | yes |

### Ranked full-text search = sparse vectors (BM25 / SPLADE / miniCOIL)

BM25 collection setup (IDF modifier required):
```json
PUT /collections/books
{ "sparse_vectors": { "title-bm25": { "modifier": "idf" } } }
```
```python
client.create_collection(
    collection_name="books",
    sparse_vectors_config={"title-bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)},
)

# ingest (server-side/FastEmbed inference via Document)
client.upsert(
    collection_name="books",
    points=[models.PointStruct(
        id=1,
        vector={"title-bm25": models.Document(text="The Time Machine", model="qdrant/bm25")},
        payload={"title": "The Time Machine", "author": "H.G. Wells"},
    )],
)

# query
client.query_points(
    collection_name="books",
    query=models.Document(text="time travel", model="qdrant/bm25"),
    using="title-bm25",
    limit=10,
    with_payload=True,
)
```
BM25 options (must match at ingest and query time): `k` (default 1.2, term-frequency saturation), `b` (default 0.75, length normalization), `avg_len` (default 256), `language` (default english; drives stemmer+stopwords), `stemmer` (`{"type":"none"}` to disable), `stopwords`, `tokenizer` (`word` default | `multilingual` for non-Latin scripts), `ascii_folding`. Pass via `models.Document(..., options={"language": "spanish"})` or `options=models.Bm25Config(...)`. SPLADE: `model="prithivida/splade_pp_en_v1"` (semantic term expansion, weaker on out-of-vocab tokens). miniCOIL: contextual 4-d-per-term lexical model via FastEmbed. Combine any of these with dense prefetch + RRF for hybrid text search.

## 3.5 Explore API — recommend, discover, context, sampling

All served by `POST /collections/{name}/points/query`. IDs used as examples/targets are excluded from results (pass raw vectors to include them).

### Recommend

```json
{
  "query": { "recommend": {
      "positive": [100, 231],
      "negative": [718, [0.2, 0.3, 0.4, 0.5]],
      "strategy": "average_vector"
  } },
  "filter": { "must": [ { "key": "city", "match": { "value": "London" } } ] },
  "limit": 3
}
```
```python
client.query_points(
    collection_name="{collection_name}",
    query=models.RecommendQuery(recommend=models.RecommendInput(
        positive=[100, 231],
        negative=[718, [0.2, 0.3, 0.4, 0.5]],   # IDs and raw vectors mix freely
        strategy=models.RecommendStrategy.AVERAGE_VECTOR,
    )),
    query_filter=models.Filter(must=[models.FieldCondition(
        key="city", match=models.MatchValue(value="London"))]),
    limit=3,
)
```
Strategies:
- `average_vector` (default, fastest): search vector = avg(positive) + avg(positive) − avg(negative); requires ≥1 positive.
- `best_score` (v1.6+): each candidate scored vs every example, sigmoid combination of best positive vs best negative; supports negative-only queries (find most dissimilar); cost linear in example count; raise `hnsw_ef` to ≥64 (internal default 16).
- `sum_scores`: score = Σ sim(positives) − Σ sim(negatives); supports negative-only; good for relevance-feedback loops.

Options: `using="image"` for named vectors; `lookup_from={"collection": ..., "vector": ...}` to take example vectors from another collection (same dimensionality). Batch: same `searches: [...]` / `query_batch_points` mechanism as 3.1.

### Discover (v1.7+) — target + context pairs

```json
{ "query": { "discover": {
    "target": [0.2, 0.1, 0.9, 0.7],
    "context": [ { "positive": 100, "negative": 718 }, { "positive": 200, "negative": 300 } ]
} }, "limit": 10 }
```
```python
client.query_points(
    collection_name="{collection_name}",
    query=models.DiscoverQuery(discover=models.DiscoverInput(
        target=[0.2, 0.1, 0.9, 0.7],
        context=[
            models.ContextPair(positive=100, negative=718),
            models.ContextPair(positive=200, negative=300),
        ],
    )),
    limit=10,
)
```
Score = sigmoid(sim(target)) + Σ rank(pair), rank = +1 if sim(positive) ≥ sim(negative) else −1. Context wins over target. Accuracy benefits from `hnsw_ef` ≥ 128.

### Context search — pairs only, no target

```json
{ "query": { "context": [ { "positive": 100, "negative": 718 }, { "positive": 200, "negative": 300 } ] }, "limit": 10 }
```
```python
client.query_points(
    collection_name="{collection_name}",
    query=models.ContextQuery(context=[
        models.ContextPair(positive=100, negative=718),
        models.ContextPair(positive=200, negative=300),
    ]),
    limit=10,
)
```
Loss per pair = min(sim(pos) − sim(neg), 0); best score 0.0. Returns diverse points from "positive zones", not clustered around one spot.

### Random sampling — see 3.1 (`{"sample": "random"}` / `models.SampleQuery`).

### Distance Matrix API (v1.12+) — pairwise similarities of a sample (clustering/viz)

```python
client.search_matrix_pairs(collection_name="{collection_name}", sample=10, limit=2,
    query_filter=models.Filter(must=[models.FieldCondition(key="color", match=models.MatchValue(value="red"))]))
# -> {"pairs": [{"a": 1, "b": 3, "score": 1.4063}, ...]}
client.search_matrix_offsets(collection_name="{collection_name}", sample=10, limit=2)
# -> {"offsets_row": [...], "offsets_col": [...], "scores": [...], "ids": [...]}
```
REST: `POST /collections/{name}/points/search/matrix/pairs` and `/matrix/offsets`; params `sample` (vectors sampled), `limit` (top-k per sample), optional `filter`.

## 3.6 Relevance: MMR, relevance feedback, reranking

### MMR — diversity-aware selection (v1.15+)

```json
{ "query": { "nearest": [0.01, 0.45, 0.67],
             "mmr": { "diversity": 0.5, "candidates_limit": 100 } },
  "limit": 10 }
```
```python
client.query_points(
    collection_name="{collection_name}",
    query=models.NearestQuery(
        nearest=[0.01, 0.45, 0.67],
        mmr=models.Mmr(diversity=0.5, candidates_limit=100),
    ),
    limit=10,
)
```
`diversity`: 0.0 = pure relevance, 1.0 = pure diversity (λ = 1 − diversity). `candidates_limit`: pool preselected before MMR. Results are ordered by selection sequence, not by score.

### Relevance feedback (v1.17+)

Feed scores from an external feedback model (e.g. cross-encoder over top 3–5 hits) back into a second query:
```json
{ "query": { "relevance_feedback": {
    "target": [0.1, 0.9, 0.23],
    "feedback": [ { "example": 111, "score": 0.68 },
                  { "example": 222, "score": 0.72 },
                  { "example": 333, "score": 0.61 } ],
    "strategy": { "naive": { "a": 0.12, "b": 0.43, "c": 0.03 } }
} } }
```
```python
client.query_points(
    "{collection_name}",
    query=models.RelevanceFeedbackQuery(relevance_feedback=models.RelevanceFeedbackInput(
        target=[0.1, 0.9, 0.23],
        feedback=[
            models.FeedbackItem(example=111, score=0.68),
            models.FeedbackItem(example=222, score=0.72),
            models.FeedbackItem(example=333, score=0.61),
        ],
        strategy=models.NaiveFeedbackStrategy(
            naive=models.NaiveFeedbackStrategyParams(a=0.12, b=0.43, c=0.03)),
    )),
)
```
Naive strategy: score = a·sim(query, cand) + Σ confidence^b · c · (sim(pos,cand) − sim(neg,cand)). a/b/c must be tuned per retriever+feedback-model+collection (helper package: `qdrant-relevance-feedback` on PyPI). Example IDs are excluded from results.

### Reranking recap
- **In-database**: multi-stage prefetch rescoring with ColBERT-style multivectors (see 3.3) — MaxSim late interaction, `using` a multivector field, `m=0` HNSW for rerank-only vectors.
- **Score-side**: formula queries (3.3) for business-logic boosting.
- **External**: cross-encoder rerankers over Qdrant top-k, optionally closed-loop via relevance feedback.

## 3.7 Search-time performance: params, exact mode, low latency

### SearchParams

```json
"params": {
  "hnsw_ef": 128,
  "exact": false,
  "indexed_only": false,
  "quantization": { "ignore": false, "rescore": true, "oversampling": 2.0 }
}
```
```python
search_params=models.SearchParams(
    hnsw_ef=128,          # search-time beam size; higher = better recall, slower.
                          # Unset -> collection's hnsw_config.ef_construct-governed default
    exact=False,          # True = full-scan exact kNN, ignores HNSW (ground truth / benchmarks)
    indexed_only=False,   # True (v1.7+) = skip unindexed segments; freshest points may be missing
    quantization=models.QuantizationSearchParams(
        ignore=False,       # True bypasses quantized index, uses originals only
        rescore=True,       # re-score top-k with originals (default on for binary/1-2 bit quant)
        oversampling=2.0,   # float >= 1.0 (default 1.0); limit*oversampling candidates pre-rescore
    ),
)
```

### Exact search
`"params": {"exact": true}` — brute-force over original vectors; use for ground-truth recall measurement or tiny/heavily-filtered collections, not production traffic.

### Low-latency checklist (docs guidance)
- Payload-index every filtered field BEFORE ingest; strict mode can reject unindexed-field filters (surface errors, not latency spikes).
- Scale reads with shard replicas; replicas serve reads in parallel (writes get costlier).
- Delayed fan-out (v1.17+): re-issue reads to another replica if the first exceeds a threshold — `client.update_collection(collection_name=..., collection_params=models.CollectionParamsDiff(read_fan_out_delay_ms=100))`; set near your p95, `0` disables.
- `indexed_only=True` avoids scanning fresh unindexed segments; `prevent_unoptimized` (v1.17.1+, experimental) defers points until optimized (use `wait=false` on writes).
- Read affinity (v1.19+): `X-Qdrant-Route-Affinity` header with a stable client ID pins a client's reads to one replica for consistent views.
- Latency-first: many small segments (parallel per-segment search); throughput-first: fewer large segments. Tune `hnsw_ef` down for latency, up for recall; quantization + `oversampling`/`rescore` trades RAM/speed vs accuracy.


---

# Part 4 — Embeddings & Tooling: Inference, FastEmbed, MCP, Edge

## 4.1 Inference API (server-side embeddings)

Docs: https://qdrant.tech/documentation/inference/inference-api/ — pass **Inference Objects** (`Document`, `Image`) instead of raw vectors; Qdrant embeds them server-side (Qdrant Cloud Inference, external providers, or the BM25 model) at upsert and query time.

**Availability: Qdrant Managed Cloud only** for model inference (enable in the **Inference tab** of the Cluster Detail page; some models are free, incl. on free-tier clusters). Exception: `Qdrant/bm25` sparse inference is executed locally by the cluster itself. Note: when using the Python client against a **local** Qdrant, `Document`/`Image` objects are instead embedded client-side via the FastEmbed integration (`pip install "qdrant-client[fastembed]"`) — same API shape, local computation.

Client must be created with `cloud_inference=True`:

```python
from qdrant_client import QdrantClient, models

client = QdrantClient(
    url="https://xyz-example.qdrant.io:6333",
    api_key="<your-qdrant-api-key>",
    cloud_inference=True,
)
```

Inference object shapes: `Document(text=..., model=..., options={})` and `Image(image=<url or base64 data-URL>, model=..., options={})`.

Upsert mixing multiple models/named vectors in one point:

```python
client.upsert(
    collection_name="{collection_name}",
    points=[
        models.PointStruct(
            id=1,
            vector={
                "image": models.Image(
                    image="https://qdrant.tech/example.png",
                    model="jinaai/jina-clip-v2",
                    options={"jina-api-key": "<your_jinaai_api_key>", "dimensions": 512},
                ),
                "text": models.Document(
                    text="Mars, the red planet",
                    model="sentence-transformers/all-minilm-l6-v2",
                ),
                "bm25": models.Document(text="Mars, the red planet", model="Qdrant/bm25"),
            },
        )
    ],
)
```

Query:

```python
client.query_points(
    collection_name="{collection_name}",
    query=models.Document(text="My Query Text", model="<the-model-to-use>"),
)
```

Key facts:
- **Input text is NOT stored** — put it in `payload` explicitly if you need it back.
- Identical inference objects in one request are **deduplicated** (embedded once).
- Short search queries may be embedded locally by cloud for latency; long inputs/upserts routed to the inference service.
- Cloud-hosted model examples: `sentence-transformers/all-minilm-l6-v2`, `qdrant/clip-vit-b-32-text` / `qdrant/clip-vit-b-32-vision` (CLIP text↔image), E5-family, `qdrant/bm25`. Full list + dims: Cluster Detail → Inference tab.

## 4.2 BM25 (sparse, server-side)

Docs: https://qdrant.tech/documentation/inference/inference-bm25/ — model `Qdrant/bm25` produces **sparse vectors** (one dimension per word). Runs on the cluster itself (no external model host). Collection needs a **sparse vector** config; then:

```python
# upsert
client.upsert(
    collection_name="{collection_name}",
    points=[models.PointStruct(
        id=1,
        vector={"my-bm25-vector": models.Document(
            text="Recipe for baking chocolate chip cookies", model="Qdrant/bm25")},
    )],
)
# query — note `using=` selects the named sparse vector
client.query_points(
    collection_name="{collection_name}",
    query=models.Document(text="How to bake cookies?", model="Qdrant/bm25"),
    using="my-bm25-vector",
)
```

Related sparse models via FastEmbed/local: `prithivida/Splade_PP_en_v1` (SPLADE) and `Qdrant/minicoil-v1` (miniCOIL — "BM25 that understands contextual meaning of keywords"). miniCOIL **requires the IDF modifier**:

```python
client.create_collection(
    collection_name="{minicoil_collection_name}",
    sparse_vectors_config={"minicoil": models.SparseVectorParams(modifier=models.Modifier.IDF)},
)
# upsert with options={"avg_len": avg_documents_length}; query with model="Qdrant/minicoil-v1", using="minicoil"
```

## 4.3 Cloud Inference vs External Providers

**External providers** (cloud only): OpenAI, Cohere, Jina AI, OpenRouter. Model name is prefixed: `openai/text-embedding-3-large`, `cohere/embed-v4.0`, `jinaai/jina-clip-v2`, `openrouter/mistralai/mistral-embed-2312`. Your provider API key is passed **per request** (Qdrant never stores it) — either as a context header (`openai-api-key`, `cohere-api-key`, `jina-api-key`, `openrouter-api-key`) or inside the vector's `options`:

```python
from qdrant_client import QdrantClient, models
from qdrant_client.context_headers import headers

client = QdrantClient(url="https://xyz-example.qdrant.io:6333",
                      api_key="<your-qdrant-api-key>", cloud_inference=True)

with headers({"openai-api-key": "<YOUR_OPENAI_API_KEY>"}):
    client.upsert(
        collection_name="{collection_name}",
        points=[models.PointStruct(
            id=1,
            vector=models.Document(text="Recipe for baking chocolate chip cookies",
                                   model="openai/text-embedding-3-large"),
        )],
    )
```

Provider notes:
- **OpenAI**: `options={"dimensions": N}` for dim reduction.
- **Cohere**: only Embed API **v2**; multimodal images must be **base64 data-URLs** (not URLs); `options={"output_dimension": 512}`.
- **Jina**: image **URLs allowed**; `options={"dimensions": 512}`.
- Collection dimensionality must match the model's output.

## 4.4 Matryoshka models

Docs: https://qdrant.tech/documentation/inference/matryoshka-models/ — MRL models produce truncatable vectors. On Qdrant Cloud, e.g. `openai/text-embedding-3-small` with `options={"mrl": 64}` — one inference call yields the full vector plus reduced sizes (cheaper/faster). Pattern: store both named vectors, prefetch ~1000 candidates on the small ("mrl") vector, re-score with the full one:

```python
with headers({"openai-api-key": "<YOUR_OPENAI_API_KEY>"}):
    client.upsert(
        collection_name="{collection_name}",
        points=[models.PointStruct(
            id=1,
            vector={
                "large": models.Document(text="Recipe for baking chocolate chip cookies",
                                         model="openai/text-embedding-3-small"),
                "small": models.Document(text="Recipe for baking chocolate chip cookies",
                                         model="openai/text-embedding-3-small",
                                         options={"mrl": 64}),
            },
        )],
    )
```

## 4.5 FastEmbed (local, CPU-first embedding library)

`pip install fastembed` (GPU: `pip install fastembed-gpu`). ONNX-based, lighter than Transformers/Sentence-Transformers. Runs fully **locally** — no cloud needed.

### Basic usage

Default model **`BAAI/bge-small-en-v1.5` — 384 dims**:

```python
from fastembed import TextEmbedding

documents = ["FastEmbed is lighter than Transformers & Sentence-Transformers.",
             "FastEmbed is supported by and maintained by Qdrant."]
embedding_model = TextEmbedding()          # BAAI/bge-small-en-v1.5
embeddings = list(embedding_model.embed(documents))   # np.ndarray, shape (384,)
```

Enumerate models per class: `TextEmbedding.list_supported_models()`, `SparseTextEmbedding.list_supported_models()`, `LateInteractionTextEmbedding.list_supported_models()`, `TextCrossEncoder.list_supported_models()`.

### Model families (names / dims / sizes)

| Family | Class | Examples |
|---|---|---|
| Dense text | `TextEmbedding` | `BAAI/bge-small-en-v1.5` (384d, default), `sentence-transformers/all-MiniLM-L6-v2` (384d) |
| Sparse | `SparseTextEmbedding` | `Qdrant/bm25`, `prithivida/Splade_PP_en_v1` (vocab 30,522, 0.53 GB), `Qdrant/minicoil-v1` |
| Late interaction | `LateInteractionTextEmbedding` | `colbert-ir/colbertv2.0` (128d/token, 0.44 GB), `answerdotai/answerai-colbert-small-v1` (96d/token, 0.13 GB) |
| Rerankers (cross-encoders) | `TextCrossEncoder` | `Xenova/ms-marco-MiniLM-L-6-v2` (0.08 GB), `Xenova/ms-marco-MiniLM-L-12-v2` (0.12 GB), `BAAI/bge-reranker-base` (1.04 GB), `jinaai/jina-reranker-v1-tiny-en` (0.13 GB), `jinaai/jina-reranker-v1-turbo-en` (0.15 GB), `jinaai/jina-reranker-v2-base-multilingual` (1.11 GB, CC-BY-NC) |
| Multimodal (CLIP) | `TextEmbedding` / `ImageEmbedding` | `Qdrant/clip-ViT-B-32-text`, `Qdrant/clip-ViT-B-32-vision` |

### qdrant-client integration (implicit inference)

`pip install "qdrant-client[fastembed]>=1.14.2"` — pass `models.Document` and the client embeds locally with FastEmbed (works with `:memory:`, local server, or cloud):

```python
from qdrant_client import QdrantClient, models

client = QdrantClient(":memory:")
model_name = "BAAI/bge-small-en"

client.create_collection(
    collection_name="test_collection",
    vectors_config=models.VectorParams(
        size=client.get_embedding_size(model_name),   # auto dim lookup
        distance=models.Distance.COSINE),
)
client.upload_collection(
    collection_name="test_collection",
    vectors=[models.Document(text=doc, model=model_name) for doc in docs],
    payload=metadata_with_docs, ids=ids,
)
hits = client.query_points(
    collection_name="test_collection",
    query=models.Document(text="Which integration is best for agents?", model=model_name),
).points
```

### SPLADE (sparse)

```python
from fastembed import SparseTextEmbedding
model = SparseTextEmbedding(model_name="prithivida/Splade_PP_en_v1")
sparse = list(model.embed(documents, batch_size=6))
# each SparseEmbedding has .indices (vocab positions) and .values (unnormalized weights)
# does automatic term expansion to semantically related tokens
```

### ColBERT (late interaction)

One vector **per token**; requires multivector config with MAX_SIM:

```python
client.create_collection(
    collection_name="movies",
    vectors_config=models.VectorParams(
        size=128, distance=models.Distance.COSINE,
        multivector_config=models.MultiVectorConfig(
            comparator=models.MultiVectorComparator.MAX_SIM)),
)
# docs: embedding_model.embed(descriptions)   queries: embedding_model.query_embed(text)
client.query_points(collection_name="movies",
    query=list(embedding_model.query_embed("A movie for kids with fantasy elements"))[0],
    limit=1, with_payload=True)
```

Recommended as a **reranker over 100–500 dense-retrieved candidates**, not first-stage retrieval. For scale, MUVERA postprocessing (`fastembed>=0.7.2`, `from fastembed.postprocess import Muvera`) flattens multivectors into single fixed-dim vectors for HNSW prefetch, then reranks with the original multivectors (`prefetch=models.Prefetch(query=query_muvera, using="muvera", limit=20)` then `query=query_multivec, using="colbert"`).

### Reranking (cross-encoders)

```python
from fastembed import TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder

dense_embedding_model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
reranker = TextCrossEncoder(model_name="jinaai/jina-reranker-v2-base-multilingual")

# stage 1: dense retrieval, limit=10
query_embedded = list(dense_embedding_model.query_embed(query))[0]
initial = client.query_points(collection_name="movies", using="embedding",
                              query=query_embedded, with_payload=True, limit=10)
# stage 2: rerank hit texts
new_scores = list(reranker.rerank(query, description_hits))
ranking = sorted(enumerate(new_scores), key=lambda x: x[1], reverse=True)
```

### Optimization

- `parallel`: `None` = sequential, `0` = all cores, `N` = N workers. `embed(docs, batch_size=256, parallel=4)`.
- `batch_size` defaults: 256 (text), 16 (images); client-side `QdrantClient(..., local_inference_batch_size=256)` (default 8).
- Lazy loading: `options={"lazy_load": True}` on `Document` (or `TextEmbedding(lazy_load=True)`) — skip loading model in main process when using workers.
- GPU: `fastembed-gpu`, then `TextEmbedding(model_name=..., cuda=True, device_ids=[0, 1])` for multi-GPU worker spread.
- `client.upload_points(collection_name=..., points=points, parallel=4)`.

## 4.6 Qdrant MCP server (`mcp-server-qdrant`)

Repo: https://github.com/qdrant/mcp-server-qdrant — semantic memory layer over Qdrant for MCP clients. Embeds with **FastEmbed** (default `EMBEDDING_PROVIDER=fastembed`, model `sentence-transformers/all-MiniLM-L6-v2`), so it works against local or cloud Qdrant.

**Tools:**
- `qdrant-store` — args: `information` (str), `metadata` (JSON, optional), `collection_name` (required unless a default is set).
- `qdrant-find` — args: `query` (str), `collection_name`; returns matches as separate messages.

**Env vars:** `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_LOCAL_PATH` (local file mode, alternative to URL), `COLLECTION_NAME`, `EMBEDDING_PROVIDER` (default fastembed), `EMBEDDING_MODEL` (default sentence-transformers/all-MiniLM-L6-v2), `TOOL_STORE_DESCRIPTION` / `TOOL_FIND_DESCRIPTION` (customize tool prompts — key trick for repurposing, e.g. code-snippet memory), `QDRANT_SEARCH_LIMIT` (10), `QDRANT_READ_ONLY` (false). FastMCP vars: `FASTMCP_SERVER_HOST/PORT`, `FASTMCP_LOG_LEVEL`, etc.

**Transports:** `--transport stdio` (default, local clients) | `sse` | `streamable-http` (remote clients). SSE endpoint: `http://localhost:8000/sse`.

Run: `QDRANT_URL="http://localhost:6333" COLLECTION_NAME="my-collection" uvx mcp-server-qdrant` (or Docker with `FASTMCP_SERVER_HOST=0.0.0.0`, port 8000).

Claude Desktop config:

```json
{
  "qdrant": {
    "command": "uvx",
    "args": ["mcp-server-qdrant"],
    "env": {
      "QDRANT_URL": "https://xyz-example.eu-central.aws.cloud.qdrant.io:6333",
      "QDRANT_API_KEY": "your_api_key",
      "COLLECTION_NAME": "your-collection-name",
      "EMBEDDING_MODEL": "sentence-transformers/all-MiniLM-L6-v2"
    }
  }
}
```

(Local variant: replace `QDRANT_URL`/`QDRANT_API_KEY` with `QDRANT_LOCAL_PATH: "/path/to/qdrant/database"`.)

Claude Code:

```shell
claude mcp add code-search \
  -e QDRANT_URL="http://localhost:6333" \
  -e COLLECTION_NAME="code-repository" \
  -e EMBEDDING_MODEL="sentence-transformers/all-MiniLM-L6-v2" \
  -e TOOL_STORE_DESCRIPTION="Store code snippets..." \
  -e TOOL_FIND_DESCRIPTION="Search for relevant code..." \
  -- uvx mcp-server-qdrant
```

Cursor/Windsurf: run with `--transport sse`, point IDE at `http://localhost:8000/sse`. VS Code: `.vscode/mcp.json` with `"command": "uvx", "args": ["mcp-server-qdrant"]` and `${input:...}` prompts. Smithery: `npx @smithery/cli install mcp-server-qdrant --client claude`.

## 4.7 Agent Skills

Docs: https://qdrant.tech/documentation/skills/ | catalog https://skills.qdrant.tech/ | repo https://github.com/qdrant/skills. Structured knowledge files that make coding agents act as Qdrant solutions architects ("a navigation and decision layer", not doc copies). Install the meta-advisor:

```bash
npx skills add qdrant/skills/meta/qdrant-advisor
```

Hub skills: `qdrant-clients-sdk` (Python/TS/Rust/Go/.NET/Java setup), `qdrant-scaling`, `qdrant-performance-optimization`, `qdrant-search-quality`, `qdrant-monitoring`, `qdrant-deployment-options`, `qdrant-edge`, `qdrant-model-migration`, `qdrant-version-upgrade`. Doc search endpoint: `https://skills.qdrant.tech/search?query=...`.

## 4.8 Qdrant Edge (embedded / on-device, beta)

Docs: https://qdrant.tech/documentation/edge/edge-quickstart/ — embedded vector DB running **inside your process**, local disk storage. Packages: **`qdrant-edge-py`** (PyPI), **`qdrant-edge`** (crates.io).

```python
from qdrant_edge import EdgeShard, EdgeConfig, EdgeVectorParams, Distance, Point, UpdateOperation, Query, QueryRequest
from pathlib import Path

Path("./qdrant-edge-directory").mkdir(parents=True, exist_ok=True)
config = EdgeConfig(vectors={"my-vector": EdgeVectorParams(size=4, distance=Distance.Cosine)})
edge_shard = EdgeShard.create("./qdrant-edge-directory", config)

edge_shard.update(UpdateOperation.upsert_points([
    Point(id=1, vector={"my-vector": [0.1, 0.2, 0.3, 0.4]}, payload={"color": "red"})]))

results = edge_shard.query(QueryRequest(
    query=Query.Nearest([0.2, 0.1, 0.9, 0.7], using="my-vector"),
    limit=10, with_vector=False, with_payload=True))
```

Differences vs server: no background optimizer (call `optimize()` manually), no automatic payload indexing, all calls synchronous, WAL config Rust-only.

**On-device embeddings**: `pip install fastembed qdrant-edge-py`; pre-cache `Qdrant/clip-ViT-B-32-text` + `Qdrant/clip-ViT-B-32-vision` with `TextEmbedding/ImageEmbedding(model_name=..., cache_dir=MODELS_DIR)`, then load offline with `local_files_only=True` and upsert `embeddings.tolist()`.

**On-device BM25**: built-in `Bm25`/`Bm25Config` (Python) — same token IDs and scoring as server text-search, so server snapshots query locally without re-indexing. Sparse vectors need `Modifier.Idf`. Config: language, `k=1.2`, `b=0.75`, `avg_len=256`, tokenizer (`prefix`/`whitespace`/`word`/`multilingual`), stemming/stopwords. Always `embed_document()` for docs, `embed_query()` for queries (different term weighting).

**Server sync patterns**: two shards on device — a **mutable** shard for local writes and an **immutable** shard mirroring the server. Server→Edge: full shard snapshot to initialize (`GET /collections/{name}/shards/0/snapshot`), then periodic **partial snapshots** (`POST .../shards/0/snapshot/partial/create` with the local manifest, returns only changed segments). Edge→Server: dual-write — queue local points (timestamped), background worker batch-`upsert()`s to the server, then delete synced points from the mutable shard by timestamp filter. Query both shards, dedupe by point ID. Enables offline-first apps that offload indexing to the server.

## Cloud vs Local quick matrix

| Feature | Local/self-hosted | Qdrant Cloud |
|---|---|---|
| FastEmbed client-side embedding (`Document` via `qdrant-client[fastembed]`) | Yes | Yes |
| Server-side Cloud Inference (`cloud_inference=True`, hosted models) | No | Yes (Managed Cloud; some models free) |
| External providers (openai/, cohere/, jinaai/, openrouter/) | No (call provider yourself) | Yes (key per request) |
| Matryoshka `mrl` option | No | Yes (e.g. openai/text-embedding-3-small) |
| BM25 / SPLADE / miniCOIL sparse | Yes (FastEmbed local) | Yes (`Qdrant/bm25` runs on cluster) |
| MCP server | Yes (QDRANT_LOCAL_PATH or URL) | Yes (URL + API key) |
| Qdrant Edge | On-device (beta) | Syncs with any server incl. cloud |


---

# Part 5 — Operations, Cloud, Tutorials & Integrations

## 5.1 Security & Authentication

Self-hosted Qdrant is **not secure by default** — no auth, no TLS until configured. Never expose the internal gRPC port 6335 publicly.

### API key (self-hosted)

```yaml
service:
  api_key: your_secret_api_key_here
  read_only_api_key: your_secret_read_only_api_key_here   # optional, coexists with admin key
```

Env var / Docker equivalents:

```bash
export QDRANT__SERVICE__API_KEY=your_secret_api_key_here
export QDRANT__SERVICE__READ_ONLY_API_KEY=...
docker run -p 6333:6333 -e QDRANT__SERVICE__API_KEY=your_secret_api_key_here qdrant/qdrant
```

Send the key as header `api-key: <key>` or `Authorization: Bearer <key>`. Clients:

```python
from qdrant_client import QdrantClient
client = QdrantClient(url="https://xyz-example.eu-central.aws.cloud.qdrant.io:6333",
                      api_key="your_api_key_here")
```

```typescript
import { QdrantClient } from "@qdrant/js-client-rest";
const client = new QdrantClient({ url: "https://...", port: 6333, apiKey: "..." });
```

Go: `qdrant.NewClient(&qdrant.Config{Host: "...", Port: 6334, APIKey: "...", UseTLS: true})`.

### TLS

```yaml
service:
  enable_tls: true
  verify_https_client_certificate: false   # true = mTLS client cert validation
tls:
  cert: ./tls/cert.pem
  key: ./tls/key.pem
  ca_cert: ./tls/cacert.pem
cluster:
  p2p:
    enable_tls: true      # inter-node TLS
```

API keys travel in headers — without TLS they're plaintext.

### JWT / RBAC (self-hosted)

```yaml
service:
  api_key: your_secret_api_key_here   # becomes the JWT signing secret
  jwt_rbac: true
```

(or `QDRANT__SERVICE__JWT_RBAC=true`). JWT payload claims:

- `exp` — Unix timestamp expiry (seconds)
- `access` — `"r"` (global read-only), `"m"` (manage), or a per-collection list with `rw`/`r`
- `value_exists` — token valid only while a matching point exists in a collection (revocation via data)

Generate: `jwt encode --payload '{"access": "r", "exp": 1766055305}' --secret 'your-api-key'`; pass the JWT as the api-key/Bearer value.

## 5.2 Configuration

Load order (later overrides earlier): built-in defaults → `config/config.yaml` → `config/{RUN_MODE}.yaml` → `config/local.yaml` → `--config-path` file → **env vars (highest)**.

Env var format: `QDRANT__` prefix, `__` for nesting — `QDRANT__SERVICE__API_KEY=secret`, `QDRANT__LOG_LEVEL=INFO`, `QDRANT__TLS__CERT=./tls/cert.pem`, `QDRANT__CLUSTER__ENABLED=true`.

Key options:

| YAML key | Default | Meaning |
|---|---|---|
| `storage.storage_path` | `./storage` | data dir |
| `storage.snapshots_path` | `./snapshots` | snapshot dir |
| `service.http_port` | 6333 | REST |
| `service.grpc_port` | 6334 | gRPC |
| `cluster.p2p.port` | 6335 | internal cluster comms |
| `service.max_request_size_mb` | 32 | upload batch cap |
| `service.enable_cors` | true | CORS |
| `storage.wal.wal_capacity_mb` | 32 | WAL segment size |
| `storage.performance.max_search_threads` | 0 (auto) | search threadpool |
| `telemetry_disabled` | false | opt out of anonymous usage reporting |
| `service.api_key` / `read_only_api_key` | unset | auth |

## 5.3 Optimization — memory vs speed

Three canonical setups (newer docs use memory tiers `memory: "cold"` = on-disk / `"pinned"` = RAM; classic equivalents are `on_disk: true` on vectors/HNSW and `quantization_config.always_ram: true`):

1. **High speed + low memory** — originals on disk, quantized copies in RAM:
   `vectors.memory: "cold"` (`on_disk: true`) + `quantization_config: {scalar: {type: "int8", memory: "pinned"}}` (`always_ram: true`). Optionally `params.quantization.rescore: false` for extra speed at slight precision cost.
2. **High precision + low memory** — vectors **and** HNSW on disk: `vectors.memory: "cold"` + `hnsw_config.memory: "cold"` (`hnsw_config.on_disk: true`); raise `m: 64`, `ef_construct: 512` for precision. Speed is then bounded by disk IOPS. v1.16+: `inline_storage` with quantization cuts IO ops at 3–4x storage cost.
3. **High precision + high speed** — everything in RAM + int8 scalar quantization with rescoring; tune search-time `hnsw_ef` (higher = more accurate, slower), `exact: true` only for ground-truth checks.

Latency vs throughput: many segments ≈ CPU cores (`optimizers_config.default_segment_number: 16`) minimizes latency; few large segments (`default_segment_number: 2`, `max_segment_size: 5000000`) maximizes throughput.

### Performance FAQ highlights

- Vectors dominate memory. Reduce via quantization or on-disk storage. High RSS is normal — Qdrant caches disk data aggressively ("unused RAM is wasted RAM"); use container memory limits for hard caps.
- Storage-optimized nodes want local SSDs with **≥ 50k IOPS**.
- Heavy read+write contention, in order of impact: `prevent_unoptimized` + `wait=false` writes; smaller batches; cap `optimizer_cpu_budget` (~50% vCPUs); `max_optimization_threads: 1` per shard; `read_fan_out_delay_ms` for replica failover; scale out.
- Slow queries: usually a missing payload index on a filtered field, slow disk with on-disk vectors, or oversized `limit`/`offset`.

## 5.4 Snapshots & Backups

Per-collection:

- Create `POST /collections/{name}/snapshots` — Python `client.create_snapshot(collection_name=...)`
- List `GET /collections/{name}/snapshots`; download `GET /collections/{name}/snapshots/{snapshot_name}`
- Restore: `PUT /collections/{name}/snapshots/recover` with `{"location": "<http URL or file:// URI>"}`, or upload the file via `POST /collections/{name}/snapshots/upload`

Full-storage (single-node only): `POST /snapshots` (`client.create_full_snapshot()`); restore at startup with `./qdrant --snapshot /path/file.snapshot:collection_name`.

Caveats: distributed clusters need per-node snapshots (no full-storage snapshot); snapshots restore only to the same or next minor version; when recovering into a cluster use recovery priority `snapshot` (default `replica` prefers existing data). Snapshots land in `storage.snapshots_path` (`/qdrant/snapshots` in Docker); v1.10+ can write to S3 via `snapshots_config` (bucket, region, credentials, endpoint). Qdrant Cloud free tier: manual snapshot/restore via API only; paid tiers add scheduled backups + disaster recovery.

## 5.5 Distributed Deployment

Enable: `cluster.enabled: true` (`QDRANT__CLUSTER__ENABLED=true`). First node `./qdrant --uri 'http://node1:6335'`; others join with `--bootstrap 'http://node1:6335'`. Consensus over p2p port 6335 (`cluster.consensus.tick_period_ms: 100`).

- **Sharding**: default `shard_number` = node count at collection creation; immutable without recreation (self-hosted) — Cloud v1.13+ supports live resharding. Rule of thumb: ≥ 2 shards/node; 12 shards divides evenly across 1/2/3/6/12 nodes. Custom sharding: `sharding_method: "custom"`, create keys via `PUT /collections/{name}/shards`, then upsert/query with `shard_key` (multitenancy, time-partitioning).
- **Replication**: `replication_factor` (default 1) at creation; `write_consistency_factor` controls how many replicas must ack a write. Manual replica ops via `POST /collections/{name}/cluster` with `replicate_shard` / `drop_replica` / `move_shard` (`shard_id`, `from_peer_id`, `to_peer_id`); at least one active replica must always remain. Cloud handles replication automatically. Production guidance: ≥ 3 nodes, replication_factor ≥ 2.
- **Shard transfer methods**: `stream_records` (default), `snapshot` (v1.7+, carries index + quantized data), `wal_delta` (v1.8+, only missed ops).
- **Consistency knobs at request time**: write `ordering` = `weak` | `medium` | `strong`; read `consistency` = number or `majority`/`quorum`/`all`.
- **Node removal**: move shards off, then `DELETE /cluster/peer/{peer_id}`.

## 5.6 Monitoring & Telemetry

- `GET /metrics` — Prometheus/OpenMetrics; prefix configurable via `QDRANT__SERVICE__METRICS_PREFIX`; `?per_collection=true` (v1.18+) for per-collection detail. Key families: `app_info`, `app_status_recovery_mode`, `collections_total`, `collection_points`/`collection_vectors`, `rest_responses_total`, `grpc_responses_total`, response-duration histograms, memory `*_bytes`, `cluster_enabled`, `cluster_peers_total`, `cluster_term`.
- `GET /telemetry` — detailed node report; `GET /cluster/telemetry` (v1.19+) aggregates all peers. Supports anonymization flags.
- Health probes (v1.5+, port 6333): `/healthz`, `/livez`, `/readyz` — return HTTP 200 once started; always accessible even with API-key auth enabled. Map directly to Kubernetes probes.

## 5.7 Qdrant Cloud

- **Free tier**: 1 cluster, single node, **1 GB RAM / 0.5 vCPU / 4 GB disk** (~1M × 768-dim vectors), limited regions, no dedicated resources, manual API snapshots only. Suspended after 1 week idle, deleted after 4 weeks unsuspended. No credit card required.
- **Paid (Standard)**: dedicated resources, multi-node, horizontal/vertical scaling + resharding, SLAs, scheduled backups/DR, zero-downtime upgrades for replicated clusters, GPU (AWS). Providers: AWS, GCP, Azure (+ Hybrid/Private Cloud on your own infra).
- **Create cluster**: sign up (email/Google/GitHub) at cloud.qdrant.io → name cluster, pick provider + region → Create Free Cluster. Copy the **API key shown once** at creation. Cluster URL looks like `https://xyz-example.eu-central.aws.cloud.qdrant.io` (REST 6333, gRPC 6334).
- **Database API keys**: Cluster Detail Page → API Keys → Create. Optional expiry (default 90 days), permission manage/write or read-only, optional per-collection restriction (granular keys start with `eyJhb`, need cluster ≥ v1.11). Key shown once; rotate by issuing a new key.
- **Connect**:

```python
client = QdrantClient(url="https://xyz-example.eu-central.aws.cloud.qdrant.io",
                      api_key="your-api-key")   # add cloud_inference=True to embed server-side
```

## 5.8 Tutorials — the pattern each teaches

- **Semantic search 101** (`tutorials-basics/search-beginners`): create a 384-dim cosine collection, `upload_points()` with `models.Document(text=..., model="sentence-transformers/all-minilm-l6-v2")` for automatic embedding, then `query_points()` with a text Document query; add `create_payload_index()` + filters for metadata narrowing. No manual encoding code.
- **Hybrid search + reranking** (`tutorials-basics/reranking-hybrid-search`): one collection, three named vectors — `dense` (all-MiniLM-L6-v2, cosine), `sparse` (qdrant/bm25 with IDF modifier), `multi` (ColBERT 96-dim multivector, MAX_SIM comparator, HNSW disabled since it's rerank-only). Query = two `prefetch` sub-queries (dense + sparse, top-20 each for recall), final scoring `using="multi"` so ColBERT reranks only the candidate pool — precision without paying reranker cost on the whole corpus.
- **RAG** (`tutorials-build-essentials/rag-deepseek`, agentic variants with LangGraph/CrewAI/Camel): embed docs with FastEmbed → upsert → embed query and `query_points()` for context → stuff retrieved payload text into a system-instructed prompt → send to the LLM API. Retrieval is just a pre-prompt step; Qdrant supplies the grounding text.
- **Async API** (`tutorials-develop/async-api`): swap `QdrantClient` → `AsyncQdrantClient` (qdrant-client ≥ 1.6.1) and `await` every call inside `asyncio.run(main())`; identical method surface to the sync client. Use it in ASGI web services with concurrent users — don't block threads; single-shot scripts don't need it.
- **Cluster-to-cluster migration** (`tutorials-operations/migration`): the `qdrant-migration` Docker tool streams live batches (resumable, works during active inserts, can change replication/quantization on the target):

```bash
docker run --rm -it registry.cloud.qdrant.io/library/qdrant-migration qdrant \
  --source.url 'https://src:6334' --source.api-key K1 --source.collection C \
  --target.url 'https://dst:6334' --target.api-key K2 --target.collection C \
  --migration.batch-size 64   # gRPC port 6334 required on both ends
```

## 5.9 Integrations

Ecosystem (frameworks with official Qdrant support — one line each):

| Integration | What it is |
|---|---|
| LangChain / LangChain4j | Python / Java LLM app framework; `langchain-qdrant` vector store |
| LlamaIndex | Data framework connecting private data to LLMs |
| Haystack | deepset's production LLM orchestration framework |
| CrewAI | Multi-agent workflow framework (Qdrant as agent memory/search tool) |
| LangGraph | Stateful multi-actor agent graphs (Py/JS) |
| AutoGen | Microsoft multi-agent conversation framework |
| DSPy | Algorithmic prompt/weight optimization |
| Mem0 | Self-improving memory layer for LLM apps |
| Microsoft GraphRAG / Neo4j GraphRAG | Knowledge-graph RAG pipelines |
| Semantic Router | Vector-search decision layer for routing |
| SmolAgents | Minimal code-writing agent library (HF) |
| Agno, Camel, Google ADK, Genkit, Mastra, VoltAgent, Rig-rs, Swiftide, Dynamiq | Agent/app frameworks (Python/TS/Rust) with Qdrant backends |
| Spring AI | Java/Spring AI framework |
| txtai | Semantic search + LLM workflow library |
| Cognee | AI memory: 30+ sources → graph + vector stores |
| Feast | ML feature store |
| Dagster, Lakechain, Sycamore | Data orchestration / document ETL pipelines |
| DeepEval, HoneyHive, OpenLLMetry, OpenLIT, Datadog | LLM testing & observability (traces incl. Qdrant calls) |
| Testcontainers | Throwaway Qdrant instances for tests |
| Cheshire Cat, Vanna AI, NLWeb, Fifty-One, Mirror Security | Assistants, SQL-RAG, website chat, CV datasets, vector encryption |

### Deeper: the big four + OpenAI

**LangChain** — `pip install langchain-qdrant`

```python
from langchain_qdrant import QdrantVectorStore, RetrievalMode
from langchain_openai import OpenAIEmbeddings
store = QdrantVectorStore.from_documents(
    docs, OpenAIEmbeddings(), location=":memory:",  # or url=... / path=...
    collection_name="my_documents",
)
```

`RetrievalMode.DENSE` (default) / `SPARSE` (pass `sparse_embedding`, e.g. `FastEmbedSparse`) / `HYBRID` (both, server-side fusion).

**LlamaIndex** — `pip install llama-index llama-index-vector-stores-qdrant`

```python
from llama_index.core.indices.vector_store.base import VectorStoreIndex
from llama_index.vector_stores.qdrant import QdrantVectorStore
import qdrant_client
client = qdrant_client.QdrantClient("<url>", api_key="<key>")
vector_store = QdrantVectorStore(client=client, collection_name="documents")
index = VectorStoreIndex.from_vector_store(vector_store=vector_store)
```

(`enable_hybrid=True` on QdrantVectorStore turns on hybrid dense+sparse.)

**Haystack** — `pip install qdrant-haystack`

```python
from haystack_integrations.document_stores.qdrant import QdrantDocumentStore
document_store = QdrantDocumentStore(":memory:", index="Document",
                                     embedding_dim=512, recreate_index=True)
```

Accepts all Qdrant collection settings incl. `quantization_config` (e.g. int8 scalar). Maintained by the Qdrant team.

**CrewAI** — `pip install 'crewai[tools]' 'qdrant-client[fastembed]'`
Implement a `QdrantStorage(RAGStorage)` (save/search/reset via QdrantClient + FastEmbed, auto-creates collections), then plug into memory:

```python
Crew(memory=True,
     entity_memory=EntityMemory(storage=QdrantStorage("entity")),
     short_term_memory=ShortTermMemory(storage=QdrantStorage("short-term")))
```

Tune `limit` / `score_threshold` in the search method.

**OpenAI embeddings** — `pip install openai`. `openai_client.embeddings.create(input=texts, model="text-embedding-3-small")` (1536-dim) → wrap in `PointStruct` → `upsert()`; embed the query with the same model for search. OpenAI embeddings pair well with Binary Quantization (32x size reduction, strong recall). No Anthropic embedding integration exists (Anthropic ships no embedding API); Claude appears on the LLM-generation side of RAG tutorials, with Qdrant handling retrieval as above.

## 5.10 Migrating from other vector DBs

All use the same Docker `qdrant-migration` tool with a per-source subcommand and `--<source>.*` flags plus `--qdrant.url` (gRPC :6334), `--qdrant.api-key`, `--qdrant.collection` — live streaming, resumable, index→collection one-to-one, metadata → payload. Example (Pinecone):

```bash
docker run --net=host --rm -it registry.cloud.qdrant.io/library/qdrant-migration pinecone \
  --pinecone.index-host 'https://...pinecone.io' --pinecone.index-name idx --pinecone.api-key pcsk_... \
  --qdrant.url 'https://...cloud.qdrant.io:6334' --qdrant.api-key K --qdrant.collection col
```

- **Pinecone** — serverless indexes (pod-based need extra steps); vectors, metadata, sparse values map directly; namespaces need a strategy (e.g. shard keys/payload).
- **Weaviate** — class objects → points, properties → payload.
- **Milvus** — collection → collection, fields → payload.
- **Elasticsearch / OpenSearch / Solr** — dense_vector fields → vectors, doc source → payload.
- **Chroma** — collection + metadata → collection + payload.
- **pgvector** — Postgres rows → points (vector column + selected columns as payload).
- **Redis** — vector fields from hashes/JSON → points.
- **MongoDB** — Atlas Vector Search docs → points.
- **FAISS** — index file vectors → points (IDs/payload supplied alongside).
- **S3 Vectors** — AWS S3 vector buckets → collection.
- **Qdrant → Qdrant** — cross-region/edition moves, optional target reconfiguration (replication, quantization).


---
