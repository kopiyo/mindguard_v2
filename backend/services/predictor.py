"""Model predictions using the trained MindGuard weights from Hugging Face."""

import asyncio
import logging
import time

import numpy as np
import torch

from backend.models.loader import load_model

logger = logging.getLogger(__name__)


def _predict_batch_sync(texts: list[str]) -> list[float]:
    model, tokenizer, config, device = load_model()
    max_length = int(config.get("max_length", 256))
    enc = tokenizer(
        texts,
        max_length=max_length,
        padding="max_length",
        truncation=True,
        return_tensors="pt",
    )
    enc = {key: value.to(device) for key, value in enc.items()}
    with torch.no_grad():
        outputs = model(**enc)
        probs = torch.softmax(outputs.logits, dim=1)
    return probs[:, 1].detach().cpu().tolist()


async def predict_one(text: str) -> tuple[float, float]:
    t0 = time.time()
    probs = await asyncio.to_thread(_predict_batch_sync, [text])
    ms = (time.time() - t0) * 1000
    return float(probs[0]), ms


async def predict_batch(texts: list) -> np.ndarray:
    if not texts:
        return np.array([])
    results: list[float] = []
    for i in range(0, len(texts), 16):
        results.extend(await asyncio.to_thread(_predict_batch_sync, texts[i : i + 16]))
    return np.array(results)


async def keep_space_warm() -> None:
    """Preload the local model once at startup for faster first predictions."""
    try:
        await asyncio.to_thread(load_model)
    except Exception as exc:
        logger.error("MindGuard model preload failed: %s", exc)
