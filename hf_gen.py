from typing import Optional
import os, requests

def generate_image(prompt: str, model: str) -> Optional[bytes]:
    """Return PNG/JPEG bytes from Hugging Face Inference API, or None on error."""
    token = os.getenv("HF_TOKEN")
    if not token:
        return None
    url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "image/png"}
    try:
        r = requests.post(url, headers=headers, json={"inputs": prompt}, timeout=60)
        if r.status_code == 200 and r.content:
            return r.content
        return None
    except Exception:
        return None
