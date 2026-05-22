"""ML predictions via HuggingFace Space API.

The model runs on HF's free CPU hardware; this container just
makes an HTTP request, keeping Render's 512 MB RAM limit comfortable.
"""

import asyncio
import time
import httpx
import numpy as np
import logging

logger = logging.getLogger(__name__)

_SPACE_BASE = "https://kopiyodiana-mindguard-mental-roberta.hf.space"
_SPACE_URL = f"{_SPACE_BASE}/predict"
# Cold start after sleep: Space downloads 499 MB weights — can take 3+ minutes.
_TIMEOUT = 60.0
_MAX_RETRIES = 8
_RETRY_WAIT = 30  # seconds between 503 retries


async def _call_space(inputs: list[str]) -> list[float]:
    """POST a batch of texts to the Space FastAPI endpoint and return probabilities."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await client.post(_SPACE_URL, json={"texts": inputs})
                if resp.status_code == 503:
                    wait = _RETRY_WAIT if attempt < _MAX_RETRIES - 1 else 0
                    logger.info(
                        "HF Space waking up, waiting %d s (attempt %d/%d)",
                        wait, attempt + 1, _MAX_RETRIES,
                    )
                    if wait:
                        await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()["probabilities"]
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                logger.warning("Space API error attempt %d/%d: %s", attempt + 1, _MAX_RETRIES, exc)
                if attempt == _MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(10)
    # All retries exhausted with 503 — raise so callers return 503 to the client
    # instead of silently returning 0.0 (which would produce wrong "Non-Suicidal" labels)
    raise RuntimeError("HF Space unavailable after all retries — still starting up, try again in a minute")


async def predict_one(text: str) -> tuple[float, float]:
    t0 = time.time()
    probs = await _call_space([text])
    ms = (time.time() - t0) * 1000
    return probs[0], ms


async def predict_batch(texts: list) -> np.ndarray:
    if not texts:
        return np.array([])
    results: list[float] = []
    for i in range(0, len(texts), 32):
        results.extend(await _call_space(texts[i : i + 32]))
    return np.array(results)


async def keep_space_warm() -> None:
    """Ping the Space every 8 minutes so it never sleeps (HF free tier sleeps at 15 min idle)."""
    await asyncio.sleep(60)  # let the Space finish its cold start before first ping
    while True:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.get(f"{_SPACE_BASE}/health")
            logger.debug("Space keep-warm ping sent")
        except Exception as exc:
            logger.debug("Space keep-warm ping failed (ok if starting): %s", exc)
        await asyncio.sleep(8 * 60)
