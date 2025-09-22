"""Utilities to generate idempotency keys for payloads."""

from __future__ import annotations

import hashlib
import json
from typing import Any

def compute_hash(payload: Any) -> str:
    """Compute a deterministic hash for any JSON-serialisable payload."""

    data = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(data).hexdigest()