import json
import logging
import os
import torch
from pathlib import Path
from transformers import AutoModelForSequenceClassification, AutoTokenizer, RobertaConfig, RobertaForSequenceClassification
from huggingface_hub import hf_hub_download

from backend.config import HF_CACHE_DIR, HF_REPO_ID, HF_TOKEN, MAX_LENGTH, MODEL_LOCAL_DIR, TOKENIZER_DIR

logger = logging.getLogger(__name__)

_model = None
_tokenizer = None
_config = None
_device = None
_WEIGHTS_FILE = os.getenv("HF_WEIGHTS_FILE", "mindguard_best_weights.pt")
_TOKENIZER_SUBFOLDER = os.getenv("HF_TOKENIZER_SUBFOLDER", "mindguard_tokenizer")


def _build_model_from_trained_state():
    """Create the RoBERTa-base classifier architecture without downloading a gated base model."""
    config = RobertaConfig(
        vocab_size=50265,
        max_position_embeddings=514,
        num_attention_heads=12,
        num_hidden_layers=12,
        type_vocab_size=1,
        hidden_size=768,
        intermediate_size=3072,
        num_labels=2,
    )
    return RobertaForSequenceClassification(config)


def load_model():
    global _model, _tokenizer, _config, _device

    if _model is not None:
        return _model, _tokenizer, _config, _device

    if torch.cuda.is_available():
        _device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        _device = torch.device("mps")
    else:
        _device = torch.device("cpu")

    config_path = Path(__file__).resolve().parent.parent.parent / "mindguard_model_config.json"
    if config_path.exists():
        with open(config_path) as f:
            _config = json.load(f)
    else:
        _config = {"max_length": MAX_LENGTH}

    token_kwargs = {"token": HF_TOKEN} if HF_TOKEN else {}

    # Path 1: exact trained weights from Hugging Face.
    if HF_REPO_ID:
        weights_path = hf_hub_download(
            repo_id=HF_REPO_ID,
            filename=_WEIGHTS_FILE,
            token=HF_TOKEN or None,
            cache_dir=HF_CACHE_DIR,
        )
        _tokenizer = AutoTokenizer.from_pretrained(
            HF_REPO_ID,
            subfolder=_TOKENIZER_SUBFOLDER,
            cache_dir=HF_CACHE_DIR,
            **token_kwargs,
        )
        model = _build_model_from_trained_state()
        state = torch.load(weights_path, map_location=_device, weights_only=True)
        model.load_state_dict(state)
        _model = model.to(_device)
        _model.eval()
        logger.info("Loaded MindGuard model weights from Hugging Face repo %s on %s", HF_REPO_ID, _device)
        return _model, _tokenizer, _config, _device

    # Path 2: local exact model artifacts for offline development.
    if os.path.isdir(TOKENIZER_DIR) and os.path.isdir(MODEL_LOCAL_DIR):
        _tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_DIR)
        _model = AutoModelForSequenceClassification.from_pretrained(
            MODEL_LOCAL_DIR, num_labels=2, ignore_mismatched_sizes=True,
        )
        _model = _model.to(_device)
        _model.eval()
        logger.info("Loaded MindGuard model from local artifacts on %s", _device)
        return _model, _tokenizer, _config, _device

    raise RuntimeError(
        "MindGuard trained model is not configured. Set HF_REPO_ID and HF_TOKEN if the repo is private, "
        "or provide local mindguard_model_local and mindguard_tokenizer directories."
    )
