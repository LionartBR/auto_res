import hashlib, json
from typing import Any

def compute_hash(payload: Any) -> str:
    # Mantém idempotência cruzada step+input
    data = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(data).hexdigest()