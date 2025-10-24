from __future__ import annotations
from typing import Optional, Any, Dict
from google.cloud import storage
from PIL import Image
import io, json, os, pathlib

class GCSClient:
    def __init__(self, bucket_name: Optional[str] = None):
        self.bucket_name = bucket_name or os.getenv("GCS_BUCKET")
        self._client = None
        self._bucket = None
        if self.bucket_name:
            try:
                self._client = storage.Client()
                self._bucket = self._client.bucket(self.bucket_name)
            except Exception:
                self._client = None
                self._bucket = None
        self._local_root = pathlib.Path("/tmp/gcs-sim")
        self._local_root.mkdir(parents=True, exist_ok=True)

    def _use_local(self) -> bool:
        return self._bucket is None

    def read_bytes(self, key: str) -> Optional[bytes]:
        if self._use_local():
            p = self._local_root / key
            if not p.exists():
                return None
            return p.read_bytes()
        blob = self._bucket.blob(key)
        if not blob.exists():
            return None
        return blob.download_as_bytes()

    def write_bytes(self, key: str, data: bytes) -> None:
        if self._use_local():
            p = self._local_root / key
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            return
        blob = self._bucket.blob(key)
        blob.upload_from_string(data)

    def read_json(self, key: str) -> Optional[Dict[str, Any]]:
        b = self.read_bytes(key)
        if b is None:
            return None
        try:
            return json.loads(b.decode("utf-8"))
        except Exception:
            return None

    def write_json(self, key: str, obj: Dict[str, Any]) -> None:
        data = json.dumps(obj).encode("utf-8")
        self.write_bytes(key, data)

    def read_image(self, key: str) -> Optional[Image.Image]:
        b = self.read_bytes(key)
        if b is None:
            return None
        try:
            return Image.open(io.BytesIO(b)).convert("RGB")
        except Exception:
            return None
