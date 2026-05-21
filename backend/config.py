import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

HF_TOKEN = os.getenv("HF_TOKEN", "")
HF_REPO_ID = os.getenv("HF_REPO_ID", "kopiyodiana/mindguard-mental-roberta")

BASE_MODEL = "roberta-base"
MAX_LENGTH = 256

MODEL_LOCAL_DIR = str(Path(__file__).resolve().parent.parent / "mindguard_model_local")
TOKENIZER_DIR = str(Path(__file__).resolve().parent.parent / "mindguard_tokenizer")

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
