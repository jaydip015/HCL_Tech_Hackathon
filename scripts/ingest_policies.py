"""Chunk, embed and index the policy documents; register versions in the database."""
import _bootstrap  # noqa: F401
import json

from backend.services.container import build_container

if __name__ == "__main__":
    c = build_container()
    print(json.dumps(c.retriever.build(), indent=2))
    for d in c.policy_manager.register_documents():
        print(f"  {d['doc_id']:18} v{d['version']}  chunks={d['chunk_count']}  sha256={d['sha256'][:12]}")
