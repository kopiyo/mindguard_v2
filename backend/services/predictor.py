"""ML predictions via HuggingFace Inference API (async).

Runs the model on HF's servers so this container stays under 512 MB RAM.
All functions are async — call with `await` from async FastAPI endpoints.
"""

import asyncio
import time
import httpx
import numpy as np
import logging

from backend.config import HF_TOKEN, HF_REPO_ID, BASE_MODEL

logger = logging.getLogger(__name__)

_TIMEOUT = 60.0
_MODEL_ID = HF_REPO_ID if HF_TOKEN else BASE_MODEL
_API_URL = f"https://api-inference.huggingface.co/models/{_MODEL_ID}"
_HEADERS = {"Authorization": f"Bearer {HF_TOKEN}"} if HF_TOKEN else {}


def _label_to_prob(result_list: list) -> float:
    """Extract P(suicidal) from one HF text-classification response item."""
    for item in result_list:
        label = item.get("label", "").lower()
        if label in ("label_1", "suicide", "suicidal", "positive", "1"):
            return float(item["score"])
    for item in result_list:
        label = item.get("label", "").lower()
        if label in ("label_0", "non-suicide", "non_suicide", "non-suicidal", "negative", "0"):
            return 1.0 - float(item["score"])
    return float(result_list[0]["score"]) if result_list else 0.0


async def _call_api(inputs: list[str]) -> list[float]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for attempt in range(3):
            try:
                resp = await client.post(_API_URL, headers=_HEADERS, json={"inputs": inputs})
                if resp.status_code == 503:
                    wait = min(resp.json().get("estimated_time", 20), 30)
                    logger.info("HF model loading, waiting %.0fs (attempt %d)", wait, attempt + 1)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data[0], dict):
                    data = [data]
                return [_label_to_prob(item) for item in data]
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                logger.warning("HF API error attempt %d: %s", attempt + 1, exc)
                if attempt == 2:
                    raise
                await asyncio.sleep(2)
    return [0.0] * len(inputs)


async def predict_one(text: str) -> tuple[float, float]:
    t0 = time.time()
    probs = await _call_api([text])
    ms = (time.time() - t0) * 1000
    return probs[0], ms


async def predict_batch(texts: list) -> np.ndarray:
    if not texts:
        return np.array([])
    results: list[float] = []
    for i in range(0, len(texts), 32):
        results.extend(await _call_api(texts[i : i + 32]))
    return np.array(results)
