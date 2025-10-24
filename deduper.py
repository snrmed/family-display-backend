import hashlib, json
from typing import Dict, Any

def hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]

def collect_existing_hashes(manifest: Dict[str, Any]) -> set:
    existing = set()
    for item in manifest.get("items", []):
        h = item.get("hash")
        if h:
            existing.add(h)
    return existing
