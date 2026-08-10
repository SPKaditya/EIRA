"""Phase 0: prove Qdrant Cloud round-trips through the REAL memory module —
collection + tenant indexes created, Document-pattern upsert, filtered search."""
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

import memory  # noqa: E402


def main() -> None:
    c = memory.client()  # connects + ensures collection and payload indexes
    info = c.get_collection(memory.COLLECTION)
    print(f"collection '{memory.COLLECTION}' ready, points={info.points_count}")
    print("payload indexes:", dict(info.payload_schema))

    pid = memory.upsert(
        "aditya", "preference", "Prefers short answers. Call him 'boss'."
    )
    print("upserted:", pid)

    hits = memory.search("aditya", "how should I address the user?", limit=1)
    if not hits:
        sys.exit("FAIL: no hits for the right user")
    print(f"OK  hit score={hits[0]['score']:.4f} text={hits[0]['text']!r}")

    stranger = memory.search("someone_else", "how should I address the user?", limit=1)
    if stranger:
        sys.exit("FAIL: tenant isolation broken — another user_id saw the memory")
    print("OK  tenant isolation: other user_id sees nothing")


if __name__ == "__main__":
    main()
