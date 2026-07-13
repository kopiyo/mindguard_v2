import asyncio
import io
import json
import logging
import os
import re
import secrets
import string
import subprocess
import sys
import tempfile
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

import numpy as np
import httpx
from pathlib import Path

from fastapi import FastAPI, Header, Request, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import SUPABASE_URL, SUPABASE_ANON_KEY
from backend.models.schemas import (
    TextAnalysisRequest, TextAnalysisResponse,
    PlatformRequest, LoginRequest, RegisterRequest, UserResponse,
    CreateGroupRequest, UpdateGroupRequest, AddMemberRequest,
    GroupMessageRequest, UpdateNotificationPreferenceRequest,
    MuteGroupRequest, NOTIFICATION_TYPES,
)
from backend.services.predictor import predict_one, predict_batch, keep_space_warm
from backend.utils import clean_text, risk_label, detect_socioeconomic, calibrate_risk_score, RESOURCES, US_STATE_RESOURCES, TEAM_MEMBERS
from backend.database import (
    init_db, seed_defaults,
    get_user_by_email, get_user_by_id, create_user,
    get_students, update_student_status,
    save_analysis, get_analytics,
    create_referral, get_referrals, update_referral,
    send_message, get_conversation, get_conversations, mark_read, mark_all_read,
    create_notification, get_notifications, get_notification_summary, mark_notification_read,
    get_counsellor_dashboard, accept_user_terms,
    # v1 additions
    create_consent, get_consent_by_id, get_consent_by_token,
    get_consents_by_counsellor, get_consents_by_student,
    create_linked_account, get_linked_accounts, revoke_linked_account,
    get_alerts, dispose_alert, get_open_alert_for_student,
    write_audit, get_audit_log,
    create_note, get_notes,
    update_rolling_risk, get_rolling_risk, get_rolling_risk_history,
    get_user_by_referral_code, get_all_users,
    # groups
    create_group, get_group_by_id, update_group, delete_group,
    add_group_member, remove_group_member, get_group_members,
    get_groups_for_user, is_group_member, get_group_unread_count,
    send_group_message, get_group_messages,
    mark_group_message_read, mark_all_group_messages_read,
    # notification preferences
    get_notification_preferences, set_notification_preference, should_notify,
)
from backend.services.consent_service import (
    dispatch_consent, record_view, accept_consent, decline_consent, revoke_consent,
)
from backend.services.alert_service import compute_rolling_risk, try_create_alert
from backend.auth import hash_password, verify_password, create_access_token, require_auth, blacklist_token

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="MindGuard API", version="2.0.0")


_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.on_event("startup")
async def startup():
    init_db()
    seed_defaults()
    logger.info("Database initialized and seeded")
    asyncio.create_task(keep_space_warm())


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}


# ── Rate limiting ─────────────────────────────────────────────────────

_rate_store: dict[str, list[float]] = defaultdict(list)
_RATE_WINDOW = 60   # seconds
_AUTH_RATE_MAX = 10  # max auth attempts per window per IP


def _check_rate_limit(key: str, max_requests: int = _AUTH_RATE_MAX, window: int = _RATE_WINDOW):
    now = time.time()
    _rate_store[key] = [t for t in _rate_store[key] if now - t < window]
    if len(_rate_store[key]) >= max_requests:
        raise HTTPException(429, "Too many requests. Please try again later.")
    _rate_store[key].append(now)


# ── Helpers ───────────────────────────────────────────────────────────

def _generate_referral_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "REF" + "".join(secrets.choice(alphabet) for _ in range(6))


def _safe_notify(user_id: str, title: str, message: str, ntype: str = "general"):
    """Create a notification without crashing the caller on failure."""
    try:
        create_notification(user_id, title, message, ntype)
    except Exception as e:
        logger.error("Notification creation failed for user %s: %s", user_id, e)


_PRIVATE_HOST_PATTERNS = re.compile(
    r"^(localhost|127\.|0\.0\.0\.0|::1|169\.254\.|10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.)",
    re.IGNORECASE,
)


def _validate_external_host(host: str) -> None:
    """Block SSRF by rejecting loopback and private-range hostnames."""
    host = host.strip().lower()
    if not host or len(host) > 253:
        raise HTTPException(400, "Invalid hostname")
    if _PRIVATE_HOST_PATTERNS.match(host):
        raise HTTPException(400, "Invalid hostname")
    if not re.match(r'^[a-z0-9][a-z0-9\-\.]{0,251}[a-z0-9]$', host):
        raise HTTPException(400, "Invalid hostname")


# ── Auth routes ──────────────────────────────────────────────────────

@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(f"login:{client_ip}")

    user = get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")

    token = create_access_token(user["id"], user["role_type"])
    logger.info("Login: user=%s ip=%s", user["id"], client_ip)
    return {
        "email": user["email"],
        "name": user["name"],
        "role": user["role_type"].capitalize(),
        "role_type": user["role_type"],
        "referral_code": _generate_referral_code(),
        "access_token": token,
    }


@app.post("/api/auth/register")
async def register(req: RegisterRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(f"register:{client_ip}")

    existing = get_user_by_email(req.email)
    if existing:
        raise HTTPException(400, "Email already registered")

    _role_map = {"student": "student", "counsellor": "counsellor", "counselor": "counsellor"}
    role_type = _role_map.get(req.role.lower(), "student")

    # Parental consent gate for minor students
    is_minor = False
    if role_type == "student" and req.dob:
        try:
            birth = datetime.fromisoformat(req.dob)
            age = (datetime.now(timezone.utc) - birth.replace(tzinfo=timezone.utc)).days // 365
            is_minor = age < 18
        except ValueError:
            pass
    if is_minor and not req.parent_email:
        raise HTTPException(400, "Parent or guardian email is required for students under 18")

    # Validate referral code if provided
    referred_by_id: str | None = None
    if req.referred_by:
        referrer = get_user_by_referral_code(req.referred_by)
        if referrer:
            referred_by_id = referrer["id"]

    pw_hash = hash_password(req.password)
    user = create_user(
        req.email, req.name, pw_hash, role_type=role_type,
        dob=req.dob, parent_email=req.parent_email if is_minor else None,
        referred_by=referred_by_id,
    )

    # Notify all counsellors if a minor registered so they can follow up on parental consent
    if is_minor:
        counsellors = [u for u in get_all_users() if u["role_type"] == "counsellor"]
        for c in counsellors:
            _safe_notify(c["id"], "Minor Registration", f"Student {req.name} ({req.email}) registered and is under 18. Parental consent link sent to {req.parent_email}.", "system")

    logger.info("Register: user=%s role=%s minor=%s ip=%s", user["id"], role_type, is_minor, client_ip)
    return {"ok": True, "user": user}


@app.get("/api/auth/me")
async def get_me(user: dict = Depends(require_auth)):
    return UserResponse(
        email=user["email"],
        name=user["name"],
        role=user["role_type"].capitalize(),
        role_type=user["role_type"],
        referral_code=user.get("referral_code") or _generate_referral_code(),
    )


@app.post("/api/auth/terms")
async def accept_terms(user: dict = Depends(require_auth)):
    accept_user_terms(user["id"])
    logger.info("Terms accepted: user=%s", user["id"])
    return {"ok": True}


@app.post("/api/auth/logout")
async def logout(authorization: str = Header(...), user: dict = Depends(require_auth)):
    jti = user.get("_token_jti", "")
    if jti:
        blacklist_token(jti)
    logger.info("Logout: user=%s", user["id"])
    return {"ok": True}


@app.post("/api/auth/google")
async def google_auth(data: dict, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(f"google:{client_ip}")

    access_token = data.get("access_token")
    if not access_token:
        raise HTTPException(400, "access_token required")

    try:
        from supabase import create_client
        supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        user_resp = supabase.auth.get_user(access_token)
        sb_user = user_resp.user
    except Exception as e:
        logger.warning("Google auth failed ip=%s: %s", client_ip, e)
        raise HTTPException(401, "Invalid Supabase token")

    email = (data.get("email") or sb_user.email or "").strip().lower()
    name = (data.get("name") or
            (sb_user.user_metadata.get("full_name") if sb_user.user_metadata else None) or
            email.split("@")[0].replace(".", " ").title())

    existing = get_user_by_email(email)
    if existing:
        user = existing
    else:
        create_user(email, name, "", role_type="student")
        user = get_user_by_email(email)

    token = create_access_token(user["id"], user["role_type"])
    return {
        "email": user["email"],
        "name": user["name"],
        "role": user["role_type"].capitalize(),
        "role_type": user["role_type"],
        "referral_code": _generate_referral_code(),
        "access_token": token,
    }


# ── Analysis routes ──────────────────────────────────────────────────

@app.post("/api/analysis/text")
async def analyze_text(req: TextAnalysisRequest, user: dict = Depends(require_auth)):
    try:
        prob, ms = await predict_one(req.text)
    except Exception as exc:
        logger.error("ML inference error: %s", exc)
        raise HTTPException(503, "Analysis service temporarily unavailable. Please try again in a moment.")

    cls = "Suicidal" if prob >= 0.5 else "Non-Suicidal"
    save_analysis(user["id"], "text", req.text, prob, cls)
    analytics = get_analytics(user["id"])

    return TextAnalysisResponse(prob=prob, latency_ms=ms, analytics=analytics)


@app.post("/api/analysis/image")
async def analyze_image(file: UploadFile = File(...), user: dict = Depends(require_auth)):
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
    try:
        import pytesseract
        from PIL import Image, UnidentifiedImageError
        contents = await file.read()
        if len(contents) > MAX_IMAGE_SIZE:
            raise HTTPException(413, "Image file too large (max 10 MB)")
        try:
            img = Image.open(io.BytesIO(contents)).convert("RGB")
        except UnidentifiedImageError:
            raise HTTPException(400, "Invalid or unrecognised image format")
        text = pytesseract.image_to_string(img, config="--psm 6").strip()
        if not text:
            raise HTTPException(400, "No text could be extracted from the image")

        try:
            prob, ms = await predict_one(text)
        except Exception as exc:
            logger.error("ML inference error: %s", exc)
            raise HTTPException(503, "Analysis service temporarily unavailable. Please try again in a moment.")
        cls = "Suicidal" if prob >= 0.5 else "Non-Suicidal"
        save_analysis(user["id"], "image", "[Image OCR] " + text, prob, cls)
        analytics = get_analytics(user["id"])

        return TextAnalysisResponse(prob=prob, latency_ms=ms, analytics=analytics)
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(501, "OCR not available (pytesseract not installed)")
    except Exception as e:
        logger.error("Image analysis error: %s", e)
        raise HTTPException(500, "Image analysis failed")


# ── Platform routes ──────────────────────────────────────────────────

def _build_platform_result(posts: list, platform_key: str) -> dict:
    scores = np.array([p["risk_score"] for p in posts])
    df = [
        {k: p.get(k) for k in ["text", "date", "url", "risk_score", "raw_risk_score", "low_context", "adjustment_reason", "word_count", "char_count", "subreddit", "type"]}
        for p in posts
    ]
    return {
        "df": df,
        "overall": float(np.percentile(scores, 85)) if len(scores) > 0 else 0.0,
        "n_posts": len(posts),
        "n_high": int((scores >= 0.55).sum()) if len(scores) > 0 else 0,
        "signals": detect_socioeconomic(posts),
        "platform_key": platform_key,
    }


def _run_scraper_worker(platform: str, url: str, months: int = 3) -> list:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(400, "Enter a valid profile URL")
    _validate_external_host(parsed.hostname)

    worker = Path(__file__).resolve().parent.parent / "scraper_worker.py"
    if not worker.exists():
        raise HTTPException(500, "Scraper worker is missing")

    try:
        result = subprocess.run(
            [sys.executable, str(worker), platform, url, str(months)],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(408, "Scraping timed out. Try again or use File Upload with an archive.")

    if result.returncode != 0:
        err = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "Scraper failed"
        raise HTTPException(400, err)

    try:
        data = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        logger.error("Could not parse scraper output: %s", result.stdout[:500])
        raise HTTPException(500, "Could not parse scraper output")

    if not data.get("ok"):
        raise HTTPException(400, data.get("error") or "Scraper failed")

    posts = []
    for p in data.get("posts", []):
        text = (p.get("text") or "").strip()
        if not text:
            continue
        try:
            date = datetime.fromisoformat(str(p.get("date", "")).replace("Z", "+00:00"))
        except ValueError:
            date = datetime.now(timezone.utc)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        posts.append({
            "text": text,
            "date": date.isoformat(),
            "url": p.get("url") or ("" if platform in {"facebook", "twitter"} else url),
        })
    return posts


def _login_bluesky(identifier: str, password: str) -> str:
    url = "https://bsky.social/xrpc/com.atproto.server.createSession"
    payload = json.dumps({"identifier": identifier, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "MindGuard/3.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))["accessJwt"]
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 401):
            raise HTTPException(401, f"Login failed for Bluesky handle '{identifier}'.")
        raise HTTPException(exc.code, f"Bluesky login failed with HTTP {exc.code}.")
    except Exception as exc:
        raise HTTPException(502, f"Could not reach Bluesky login API: {exc}")


def _fetch_bluesky_posts(handle: str, access_token: str) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    headers = {"User-Agent": "MindGuard/3.0", "Authorization": f"Bearer {access_token}"}
    resolve_url = "https://bsky.social/xrpc/com.atproto.identity.resolveHandle?" + urlencode({"handle": handle})
    try:
        req = urllib.request.Request(resolve_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            did = json.loads(resp.read().decode("utf-8"))["did"]
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise HTTPException(404, f"Handle not found: {handle}.")
        raise HTTPException(exc.code, f"Could not resolve Bluesky handle (HTTP {exc.code}).")
    except Exception as exc:
        raise HTTPException(502, f"Could not reach Bluesky API: {exc}")

    posts: list[dict] = []
    cursor = None

    def public_bluesky_url_available(post_url: str) -> bool:
        try:
            parsed = urlparse(post_url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                return False
            _validate_external_host(parsed.hostname)
            req = urllib.request.Request(post_url, headers={"User-Agent": "MindGuard/3.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                html = resp.read(300_000).decode("utf-8", errors="ignore").lower()
                return resp.status < 400 and "post not found" not in html
        except Exception:
            return False

    for _ in range(10):
        params = {"actor": did, "limit": 100}
        if cursor:
            params["cursor"] = cursor
        feed_url = "https://bsky.social/xrpc/app.bsky.feed.getAuthorFeed?" + urlencode(params)
        try:
            req = urllib.request.Request(feed_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise HTTPException(exc.code, f"Could not fetch Bluesky posts (HTTP {exc.code}).")
        except Exception as exc:
            raise HTTPException(502, f"Could not fetch Bluesky posts: {exc}")

        feed = data.get("feed", [])
        if not feed:
            break
        oldest_in_page = None
        for item in feed:
            post = item.get("post", {})
            record = post.get("record", {})
            created_at = record.get("createdAt", "")
            try:
                created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            oldest_in_page = created
            if created < cutoff:
                continue
            text = (record.get("text") or "").strip()
            if len(text) <= 5:
                continue
            uri = post.get("uri", "")
            rkey = uri.split("/")[-1] if uri else ""
            post_url = f"https://bsky.app/profile/{handle}/post/{rkey}"
            if not public_bluesky_url_available(post_url):
                continue
            posts.append({
                "text": text,
                "date": created.isoformat(),
                "url": post_url,
            })
        cursor = data.get("cursor")
        if not cursor:
            break
        if oldest_in_page and oldest_in_page < cutoff:
            break
    posts.sort(key=lambda p: p["date"])
    return posts


# Per-user platform results to prevent cross-user data leakage.
_platform_results: dict[str, dict] = defaultdict(dict)


def _fetch_reddit_rss_posts(username: str) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=182)
    safe_username = username.strip().lstrip("u/")
    if not re.match(r"^[A-Za-z0-9_-]{3,20}$", safe_username):
        raise HTTPException(400, "Enter a valid Reddit username.")

    feeds = [
        ("Post", f"https://www.reddit.com/user/{safe_username}/submitted/.rss"),
        ("Comment", f"https://www.reddit.com/user/{safe_username}/comments/.rss"),
    ]
    namespaces = {
        "atom": "http://www.w3.org/2005/Atom",
        "media": "http://search.yahoo.com/mrss/",
    }
    raw_posts: list[dict] = []
    seen_urls = set()

    for source_type, feed_url in feeds:
        try:
            req = urllib.request.Request(
                feed_url,
                headers={"User-Agent": "MindGuard/1.0 RSS research prototype"},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                xml_text = resp.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            raise HTTPException(exc.code, f"Could not fetch Reddit RSS feed (HTTP {exc.code}).")
        except Exception as exc:
            raise HTTPException(502, f"Could not fetch Reddit RSS feed: {exc}")

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            continue

        for entry in root.findall("atom:entry", namespaces):
            title = (entry.findtext("atom:title", default="", namespaces=namespaces) or "").strip()
            content = (entry.findtext("atom:content", default="", namespaces=namespaces) or "").strip()
            content = re.sub(r"<[^>]+>", " ", content)
            content = re.sub(r"\s+", " ", content).strip()
            published = entry.findtext("atom:published", default="", namespaces=namespaces) or ""
            updated = entry.findtext("atom:updated", default="", namespaces=namespaces) or ""
            date_text = published or updated
            try:
                created = datetime.fromisoformat(date_text.replace("Z", "+00:00"))
            except ValueError:
                created = datetime.now(timezone.utc)
            if created < cutoff:
                continue

            link = ""
            for link_el in entry.findall("atom:link", namespaces):
                href = link_el.attrib.get("href", "")
                if href and "reddit.com" in href:
                    link = href
                    break
            if not link or link in seen_urls:
                continue
            seen_urls.add(link)

            text = f"{title} {content}".strip() if source_type == "Post" else content or title
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) <= 10 or text.lower() in {"[deleted]", "[removed]"}:
                continue

            subreddit_match = re.search(r"/r/([^/]+)/", link)
            raw_posts.append({
                "text": text,
                "date": created.isoformat(),
                "url": link,
                "subreddit": subreddit_match.group(1) if subreddit_match else "",
                "type": source_type,
            })

    raw_posts.sort(key=lambda p: p["date"])
    return raw_posts


@app.post("/api/platforms/reddit")
async def analyze_reddit(req: PlatformRequest, user: dict = Depends(require_auth)):
    client_id = req.client_id or os.getenv("REDDIT_CLIENT_ID", "")
    client_secret = req.client_secret or os.getenv("REDDIT_CLIENT_SECRET", "")
    if not req.username.strip():
        raise HTTPException(400, "Reddit username is required.")

    try:
        username = req.username.strip().lstrip("u/")
        if not client_id or not client_secret:
            raw_posts = _fetch_reddit_rss_posts(username)
            if not raw_posts:
                raise HTTPException(404, f"No RSS posts found for u/{username} in the last 6 months.")

            text_col = [clean_text(p["text"]) for p in raw_posts]
            scores = await predict_batch(text_col)
            for i, p in enumerate(raw_posts):
                p.update(calibrate_risk_score(p["text"], float(scores[i])))

            result = _build_platform_result(raw_posts, "reddit")
            result["min_risk"] = req.min_risk
            result["n_show"] = req.n_show
            result["username"] = username
            result["mode"] = "rss"
            _platform_results[user["id"]]["reddit"] = result
            return result

        import praw
        import prawcore
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent="MindGuard/1.0",
        )
        redditor = reddit.redditor(username)
        cutoff = datetime.now(timezone.utc) - timedelta(days=182)

        raw_posts = []
        for submission in redditor.submissions.new(limit=200):
            created = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)
            if created < cutoff:
                break
            text = f"{submission.title} {submission.selftext or ''}".strip()
            if len(text) <= 10:
                continue
            raw_posts.append({
                "text": text,
                "date": created.isoformat(),
                "url": f"https://reddit.com{submission.permalink}",
                "subreddit": submission.subreddit.display_name,
                "type": "post",
            })
        for comment in redditor.comments.new(limit=500):
            created = datetime.fromtimestamp(comment.created_utc, tz=timezone.utc)
            if created < cutoff:
                break
            text = (comment.body or "").strip()
            if len(text) <= 10 or text in ("[deleted]", "[removed]"):
                continue
            raw_posts.append({
                "text": text,
                "date": created.isoformat(),
                "url": f"https://reddit.com{comment.permalink}",
                "subreddit": comment.subreddit.display_name,
                "type": "comment",
            })
        raw_posts.sort(key=lambda p: p["date"])

        if not raw_posts:
            raise HTTPException(404, f"No posts found for u/{username} in the last 6 months.")

        text_col = [clean_text(p["text"]) for p in raw_posts]
        scores = await predict_batch(text_col)
        for i, p in enumerate(raw_posts):
            p.update(calibrate_risk_score(p["text"], float(scores[i])))

        result = _build_platform_result(raw_posts, "reddit")
        result["min_risk"] = req.min_risk
        result["n_show"] = req.n_show
        result["username"] = username
        _platform_results[user["id"]]["reddit"] = result
        return result

    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(501, "PRAW not installed. Install with: pip install praw")
    except prawcore.exceptions.NotFound:
        raise HTTPException(404, f"Reddit user '{req.username}' not found.")
    except prawcore.exceptions.Forbidden:
        raise HTTPException(403, f"Access forbidden for Reddit user '{req.username}'.")
    except prawcore.exceptions.ResponseException as e:
        logger.error("Reddit API error: %s", e)
        raise HTTPException(502, f"Reddit API responded with an error: {e}")
    except Exception as e:
        logger.error("Reddit analysis error: %s", e)
        raise HTTPException(400, f"Reddit analysis failed: {e}")


@app.post("/api/platforms/bluesky")
async def analyze_bluesky(req: PlatformRequest, user: dict = Depends(require_auth)):
    target_handle = req.handle.strip().lstrip("@")
    login_handle = (req.identifier or req.handle).strip().lstrip("@")
    if target_handle and "." not in target_handle:
        target_handle = f"{target_handle}.bsky.social"
    if login_handle and "." not in login_handle:
        login_handle = f"{login_handle}.bsky.social"
    if not target_handle:
        raise HTTPException(400, "Enter the Bluesky handle you want to analyse.")
    if not login_handle or not req.password:
        raise HTTPException(400, "Enter your Bluesky handle and App Password.")
    try:
        access_token = await asyncio.to_thread(_login_bluesky, login_handle, req.password)
        raw_posts = await asyncio.to_thread(_fetch_bluesky_posts, target_handle, access_token)

        if not raw_posts:
            raise HTTPException(404, f"No posts found for '{target_handle}' in the last 3 months.")

        texts = [clean_text(p["text"]) for p in raw_posts]
        scores = await predict_batch(texts)
        for i, p in enumerate(raw_posts):
            p.update(calibrate_risk_score(p["text"], float(scores[i])))

        result = _build_platform_result(raw_posts, "bluesky")
        result["min_risk"] = req.min_risk
        result["n_show"] = req.n_show
        result["handle"] = target_handle
        _platform_results[user["id"]]["bluesky"] = result
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Bluesky analysis error: %s", e)
        raise HTTPException(400, f"Bluesky analysis failed: {e}")


@app.post("/api/platforms/mastodon")
async def analyze_mastodon(req: PlatformRequest, user: dict = Depends(require_auth)):
    if not req.handle:
        raise HTTPException(400, "Handle required")
    handle_input = req.handle.strip().lstrip("@")
    if "@" not in handle_input:
        raise HTTPException(400, "Mastodon handle must be in format: username@instance.social")
    parts = handle_input.split("@")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise HTTPException(400, "Mastodon handle must be in format: username@instance.social")
    username, instance = parts
    _validate_external_host(instance)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"https://{instance}/api/v1/accounts/lookup",
                params={"acct": username},
            )
            if r.status_code == 404:
                raise HTTPException(404, f"Could not find Mastodon account: {username}@{instance}")
            r.raise_for_status()
            acct = r.json()

            raw_posts = []
            max_id = None
            cutoff = datetime.now(timezone.utc) - timedelta(days=90)

            async def public_status_url_available(status_url: str) -> bool:
                if not status_url:
                    return False
                parsed_url = urlparse(status_url)
                if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
                    return False
                _validate_external_host(parsed_url.hostname)
                try:
                    check = await client.head(status_url, follow_redirects=True, timeout=8.0)
                    if check.status_code in {405, 501}:
                        check = await client.get(status_url, follow_redirects=True, timeout=8.0)
                    return 200 <= check.status_code < 400
                except Exception:
                    return False

            for _ in range(10):
                params: dict = {"limit": 40, "exclude_replies": False}
                if max_id:
                    params["max_id"] = max_id
                r = await client.get(
                    f"https://{instance}/api/v1/accounts/{acct['id']}/statuses",
                    params=params,
                )
                if r.status_code in {401, 403, 404}:
                    raise HTTPException(r.status_code, "Could not fetch Mastodon posts. The account may be private, restricted, or unavailable.")
                r.raise_for_status()
                statuses = r.json()
                if not statuses:
                    break

                for s in statuses:
                    try:
                        created = datetime.fromisoformat(s["created_at"].replace("Z", "+00:00"))
                    except (ValueError, KeyError):
                        created = datetime.now(timezone.utc)
                    if created < cutoff:
                        break
                    text = re.sub(r"<[^>]+>", "", s.get("content", "")).strip()
                    if len(text) <= 5:
                        continue
                    status_url = s.get("url", "")
                    if not await public_status_url_available(status_url):
                        continue
                    raw_posts.append({
                        "text": text,
                        "date": s.get("created_at", ""),
                        "url": status_url,
                    })
                max_id = statuses[-1]["id"]
                if raw_posts and datetime.fromisoformat(str(raw_posts[-1]["date"]).replace("Z", "+00:00")) < cutoff:
                    break

        if not raw_posts:
            raise HTTPException(404, "No posts found or account is private/not found.")

        texts = [clean_text(p["text"]) for p in raw_posts]
        scores = await predict_batch(texts)
        for i, p in enumerate(raw_posts):
            p.update(calibrate_risk_score(p["text"], float(scores[i])))

        result = _build_platform_result(raw_posts, "mastodon")
        result["min_risk"] = req.min_risk
        result["n_show"] = req.n_show
        result["handle"] = f"{username}@{instance}"
        _platform_results[user["id"]]["mastodon"] = result
        return result

    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        logger.error("Mastodon HTTP status error: %s", e)
        raise HTTPException(400, f"Mastodon API returned an error: HTTP {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error("Mastodon network error: %s", e)
        raise HTTPException(400, f"Could not reach Mastodon API: {e}")
    except Exception as e:
        logger.error("Mastodon analysis error: %s", e)
        raise HTTPException(400, f"Mastodon analysis failed: {e}")


def _download_and_transcribe_video(video_url: str, max_seconds: int = 600) -> tuple[str, str]:
    import yt_dlp
    from faster_whisper import WhisperModel

    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(tmpdir, "audio.%(ext)s"),
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
            "quiet": True,
            "noplaylist": True,
            "socket_timeout": 90,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        audio_file = next(
            (os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.endswith(".mp3")),
            None,
        )
        if not audio_file:
            raise RuntimeError("Could not download audio")

        trimmed = os.path.join(tmpdir, "trimmed.mp3")
        proc = subprocess.run(
            ["ffmpeg", "-i", audio_file, "-t", str(max_seconds), "-y", trimmed],
            capture_output=True,
            timeout=max(180, max_seconds // 2),
        )
        if proc.returncode != 0 and not os.path.exists(trimmed):
            raise RuntimeError("Audio trimming failed")

        target = trimmed if os.path.exists(trimmed) else audio_file
        whisper = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, _ = whisper.transcribe(target)
        transcript = " ".join(seg.text.strip() for seg in segments).strip()
        return transcript, target


@app.post("/api/platforms/youtube")
async def analyze_youtube(req: PlatformRequest, user: dict = Depends(require_auth)):
    if not req.channel_url:
        raise HTTPException(400, "YouTube channel or video URL required")
    try:
        api_key = req.api_key.strip()
        channel_id = None
        channel_input = req.channel_url.strip()
        lowered_input = channel_input.lower()

        is_video_url = (
            "youtube.com/watch" in lowered_input
            or "youtu.be/" in lowered_input
            or "youtube.com/shorts/" in lowered_input
            or "youtube.com/live/" in lowered_input
        )

        if is_video_url:
            transcript, _ = await asyncio.to_thread(_download_and_transcribe_video, channel_input, 600)
            if not transcript.strip():
                raise HTTPException(422, "No speech transcript was returned, so no prediction was made.")

            prob, _ = await predict_one(transcript)
            raw_posts = [{
                "text": transcript,
                "date": datetime.now(timezone.utc).isoformat(),
                "url": channel_input,
                "type": "Transcript",
                **calibrate_risk_score(transcript, float(prob)),
            }]

            result = _build_platform_result(raw_posts, "youtube")
            result["min_risk"] = req.min_risk
            result["n_show"] = req.n_show
            result["channel"] = channel_input
            result["analysis_mode"] = "video_transcript"
            _platform_results[user["id"]]["youtube"] = result
            return result

        if not api_key:
            raise HTTPException(400, "YouTube API key required for channel analysis. Direct video URLs can be analysed without an API key.")

        async with httpx.AsyncClient(timeout=10.0) as client:
            if "youtube.com/channel/" in channel_input:
                channel_id = channel_input.split("youtube.com/channel/")[-1].split("/")[0].split("?")[0]
            elif "youtube.com/@" in channel_input:
                handle = channel_input.split("youtube.com/@")[-1].split("/")[0].split("?")[0]
                r = await client.get(
                    "https://www.googleapis.com/youtube/v3/channels",
                    params={"part": "id", "forHandle": handle, "key": api_key},
                )
                r.raise_for_status()
                items = r.json().get("items", [])
                if items:
                    channel_id = items[0]["id"]
            else:
                handle = channel_input.lstrip("@")
                r = await client.get(
                    "https://www.googleapis.com/youtube/v3/channels",
                    params={"part": "id", "forHandle": handle, "key": api_key},
                )
                r.raise_for_status()
                items = r.json().get("items", [])
                if items:
                    channel_id = items[0]["id"]

            if not channel_id:
                raise HTTPException(400, "Could not resolve YouTube channel. Use a channel URL or @handle.")

            raw_posts = []
            cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
            r = await client.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part": "id,snippet",
                    "channelId": channel_id,
                    "type": "video",
                    "order": "date",
                    "maxResults": 50,
                    "publishedAfter": cutoff,
                    "key": api_key,
                },
            )
            r.raise_for_status()
            for item in r.json().get("items", []):
                vid_id = item["id"].get("videoId", "")
                snippet = item.get("snippet", {})
                title = snippet.get("title", "")
                desc = snippet.get("description", "")
                published = snippet.get("publishedAt", "")
                text = f"{title} {desc}".strip()
                if len(text) > 5:
                    raw_posts.append({
                        "text": text,
                        "date": published,
                        "url": f"https://youtube.com/watch?v={vid_id}" if vid_id else "",
                        "type": "Title/Description",
                        "video_id": vid_id,
                    })
                if not vid_id:
                    continue
                try:
                    cr = await client.get(
                        "https://www.googleapis.com/youtube/v3/commentThreads",
                        params={
                            "part": "snippet",
                            "videoId": vid_id,
                            "maxResults": 20,
                            "order": "relevance",
                            "key": api_key,
                        },
                    )
                    cr.raise_for_status()
                    for c in cr.json().get("items", []):
                        comment_text = c["snippet"]["topLevelComment"]["snippet"].get("textDisplay", "")
                        comment_text = re.sub(r"<[^>]+>", "", comment_text).strip()
                        if len(comment_text) > 5:
                            raw_posts.append({
                                "text": comment_text,
                                "date": published,
                                "url": f"https://youtube.com/watch?v={vid_id}",
                                "type": "Comment",
                                "video_id": vid_id,
                            })
                except Exception:
                    pass

            transcript_limit = min(req.transcript_limit, 3)
            if req.transcribe_videos and transcript_limit > 0:
                transcribed = 0
                videos_to_transcribe = []
                seen_video_ids = set()
                for post in raw_posts:
                    vid_id = post.get("video_id")
                    if vid_id and vid_id not in seen_video_ids:
                        seen_video_ids.add(vid_id)
                        videos_to_transcribe.append({
                            "video_id": vid_id,
                            "date": post.get("date", ""),
                            "url": post.get("url", ""),
                        })
                    if len(videos_to_transcribe) >= transcript_limit:
                        break

                for video in videos_to_transcribe:
                    try:
                        transcript, _ = await asyncio.to_thread(_download_and_transcribe_video, video["url"], 600)
                    except Exception as exc:
                        logger.warning("Could not transcribe YouTube video %s: %s", video["video_id"], exc)
                        continue
                    if len(transcript.strip()) > 5:
                        raw_posts.append({
                            "text": transcript.strip(),
                            "date": video["date"],
                            "url": video["url"],
                            "type": "Transcript",
                            "video_id": video["video_id"],
                        })
                        transcribed += 1

        if not raw_posts:
            raise HTTPException(404, "No content found in the last 3 months.")
        raw_posts.sort(key=lambda p: p["date"])

        texts = [clean_text(p["text"]) for p in raw_posts]
        scores = await predict_batch(texts)
        for i, p in enumerate(raw_posts):
            p.update(calibrate_risk_score(p["text"], float(scores[i])))

        result = _build_platform_result(raw_posts, "youtube")
        result["min_risk"] = req.min_risk
        result["n_show"] = req.n_show
        result["channel"] = channel_input
        result["transcribed_videos"] = sum(1 for p in raw_posts if p.get("type") == "Transcript")
        result["transcript_limit"] = min(req.transcript_limit, 3) if req.transcribe_videos else 0
        _platform_results[user["id"]]["youtube"] = result
        return result

    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(501, "Video processing dependencies not installed")
    except subprocess.TimeoutExpired:
        raise HTTPException(408, "Video processing timed out")
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("YouTube analysis error: %s", e)
        raise HTTPException(400, "YouTube analysis failed")


@app.post("/api/platforms/video")
async def analyze_video(req: PlatformRequest, user: dict = Depends(require_auth)):
    if not req.video_url:
        raise HTTPException(400, "Video URL required")
    try:
        transcript, _ = await asyncio.to_thread(_download_and_transcribe_video, req.video_url, 600)
        if not transcript.strip():
            raise HTTPException(422, "No speech transcript was returned, so no prediction was made.")
        prob, ms = await predict_one(transcript)
        label, color, level = risk_label(prob)
        result = {
            "ok": True,
            "risk": prob,
            "transcription": transcript,
            "label": label,
            "latency_ms": ms,
            "video_url": req.video_url,
            "signals": detect_socioeconomic([{"text": transcript}]),
        }
        _platform_results[user["id"]]["video"] = result
        return result

    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(501, "Video processing dependencies not installed")
    except subprocess.TimeoutExpired:
        raise HTTPException(408, "Video processing timed out")
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("Video analysis error: %s", e)
        raise HTTPException(400, "Video analysis failed")


@app.post("/api/platforms/facebook")
async def analyze_facebook(req: PlatformRequest, user: dict = Depends(require_auth)):
    if not req.profile_url:
        raise HTTPException(400, "Facebook profile URL is required")
    if "facebook.com" not in req.profile_url.lower():
        raise HTTPException(400, "Enter a full Facebook URL, e.g. https://www.facebook.com/username")

    try:
        raw_posts = await asyncio.to_thread(_run_scraper_worker, "facebook", req.profile_url, req.months)
        if not raw_posts:
            raise HTTPException(404, "No public posts found. The profile may be private or Facebook blocked the request.")

        texts = [clean_text(p["text"]) for p in raw_posts]
        scores = await predict_batch(texts)
        for i, p in enumerate(raw_posts):
            p.update(calibrate_risk_score(p["text"], float(scores[i])))

        result = _build_platform_result(raw_posts, "facebook")
        result["min_risk"] = req.min_risk
        result["n_show"] = req.n_show
        result["url"] = req.profile_url
        _platform_results[user["id"]]["facebook"] = result
        return result

    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(501, "Playwright is not installed. Install with: pip install playwright")
    except Exception as e:
        logger.error("Facebook analysis error: %s", e)
        raise HTTPException(400, f"Facebook analysis failed: {e}")


@app.post("/api/platforms/twitter")
async def analyze_twitter(req: PlatformRequest, user: dict = Depends(require_auth)):
    if not req.profile_url:
        raise HTTPException(400, "Twitter/X profile URL is required")
    lowered = req.profile_url.lower()
    if "twitter.com" not in lowered and "x.com" not in lowered:
        raise HTTPException(400, "Enter a valid Twitter/X URL, e.g. https://x.com/username")

    try:
        raw_posts = await asyncio.to_thread(_run_scraper_worker, "twitter", req.profile_url, 3)
        if not raw_posts:
            raise HTTPException(404, "No tweets found. The profile may be private or Twitter/X may require login.")

        texts = [clean_text(p["text"]) for p in raw_posts]
        scores = await predict_batch(texts)
        for i, p in enumerate(raw_posts):
            p.update(calibrate_risk_score(p["text"], float(scores[i])))

        result = _build_platform_result(raw_posts, "twitter")
        result["min_risk"] = req.min_risk
        result["n_show"] = req.n_show
        result["url"] = req.profile_url
        _platform_results[user["id"]]["twitter"] = result
        return result

    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(501, "Playwright is not installed. Install with: pip install playwright")
    except Exception as e:
        logger.error("Twitter/X analysis error: %s", e)
        raise HTTPException(400, f"Twitter/X analysis failed: {e}")


@app.post("/api/platforms/file")
async def analyze_file(
    file: UploadFile = File(...),
    min_risk: float = 0.0,
    n_show: int = 20,
    user: dict = Depends(require_auth),
):
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
    try:
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(413, "File too large (max 50 MB)")
        text = contents.decode("utf-8", errors="replace")
        lines = text.split("\n")

        raw_posts = []
        wa_pattern = re.compile(r"\[\d{1,2}/\d{1,2}/\d{2,4}.*?\] .*?: ")

        whatsapp_mode = bool(wa_pattern.search(text[:500]))

        if whatsapp_mode:
            current_text = ""
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                m = re.match(r"\[(.*?)\] (.*?): (.*)", line)
                if m:
                    if current_text.strip():
                        raw_posts.append({"text": current_text.strip(), "date": "", "url": ""})
                    current_text = m.group(3)
                else:
                    current_text += " " + line
            if current_text.strip():
                raw_posts.append({"text": current_text.strip(), "date": "", "url": ""})
        else:
            for line in lines:
                line = line.strip()
                if line:
                    raw_posts.append({"text": line, "date": "", "url": ""})

        if not raw_posts:
            raise HTTPException(400, "No posts found in file")

        texts = [clean_text(p["text"]) for p in raw_posts]
        scores = await predict_batch(texts)
        for i, p in enumerate(raw_posts):
            p.update(calibrate_risk_score(p["text"], float(scores[i])))

        result = _build_platform_result(raw_posts, "file")
        result["min_risk"] = min_risk
        result["n_show"] = n_show
        result["filename"] = file.filename
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("File analysis error: %s", e)
        raise HTTPException(400, "File analysis failed")


@app.get("/api/platforms/unified")
async def get_unified(user: dict = Depends(require_auth)):
    user_results = _platform_results.get(user["id"], {})
    platforms = {}
    for key in ["reddit", "bluesky", "mastodon", "youtube", "file"]:
        r = user_results.get(key)
        if r:
            platforms[key] = {
                "overall": r["overall"],
                "n_posts": r["n_posts"],
                "n_high": r["n_high"],
            }
    if user_results.get("video"):
        v = user_results["video"]
        platforms["Video"] = {"overall": v["risk"], "n_posts": 1, "n_high": 1 if v["risk"] >= 0.55 else 0}

    scores = [p["overall"] for p in platforms.values()]
    unified = float(np.mean(scores)) if scores else 0.0
    return {"platforms": platforms, "unified_score": unified}


# ── Counsellor routes ─────────────────────────────────────────────────

@app.get("/api/counsellor/students")
async def get_counsellor_students(user: dict = Depends(require_auth)):
    if user["role_type"] not in ("counsellor", "admin"):
        raise HTTPException(403, "Counsellor or admin access required")
    return get_students()


@app.post("/api/counsellor/students/approve")
async def approve_counsellor_student(data: dict, user: dict = Depends(require_auth)):
    if user["role_type"] not in ("counsellor", "admin"):
        raise HTTPException(403, "Counsellor or admin access required")
    sid = data.get("id")
    if not sid:
        raise HTTPException(400, "Student ID required")
    ok = update_student_status(sid, "approved")
    if not ok:
        raise HTTPException(404, "Student not found")
    _safe_notify(sid, "Account Approved", "Your account has been approved by a counsellor.", "approval")
    return {"ok": True}


@app.post("/api/counsellor/students/revoke")
async def revoke_counsellor_student(data: dict, user: dict = Depends(require_auth)):
    if user["role_type"] not in ("counsellor", "admin"):
        raise HTTPException(403, "Counsellor or admin access required")
    sid = data.get("id")
    if not sid:
        raise HTTPException(400, "Student ID required")
    ok = update_student_status(sid, "revoked")
    if not ok:
        raise HTTPException(404, "Student not found")
    _safe_notify(sid, "Account Revoked", "Your account access has been revoked.", "general")
    return {"ok": True}


@app.get("/api/counsellor/students/{student_id}")
async def get_student_detail(student_id: str, user: dict = Depends(require_auth)):
    if user["role_type"] not in ("counsellor", "admin"):
        raise HTTPException(403, "Counsellor or admin access required")
    student = get_user_by_id(student_id)
    if not student or student["role_type"] != "student":
        raise HTTPException(404, "Student not found")
    from backend.database import get_analyses
    analyses = get_analyses(student_id, limit=50)
    if analyses:
        latest_prob = analyses[0]["prob"]
        latest_label, latest_color, _ = risk_label(latest_prob)
    else:
        latest_prob = 0.0
        latest_label = "No data"
        latest_color = "#6b7280"
    return {
        "id": student["id"],
        "email": student["email"],
        "name": student["name"],
        "status": student["status"],
        "created_at": student["created_at"],
        "risk_summary": {
            "latest_prob": latest_prob,
            "latest_label": latest_label,
            "latest_color": latest_color,
            "total_analyses": len(analyses),
            "high_risk_count": sum(1 for a in analyses if a["prob"] >= 0.75),
        },
        "analyses": analyses,
    }


# ── Referrals routes ─────────────────────────────────────────────────

@app.get("/api/counsellor/referrals")
async def get_counsellor_referrals(user: dict = Depends(require_auth)):
    if user["role_type"] not in ("counsellor", "admin"):
        raise HTTPException(403, "Counsellor or admin access required")
    return get_referrals(user["id"])


@app.post("/api/counsellor/referrals")
async def create_counsellor_referral(data: dict, request: Request, user: dict = Depends(require_auth)):
    if user["role_type"] not in ("counsellor", "admin"):
        raise HTTPException(403, "Counsellor or admin access required")
    student_id = data.get("student_id")
    urgency = data.get("urgency", "medium")
    notes = data.get("notes", "")
    if not student_id:
        raise HTTPException(400, "Student ID required")
    if urgency not in ("low", "medium", "high", "crisis"):
        raise HTTPException(400, "Invalid urgency level")
    student = get_user_by_id(student_id)
    if not student or student["role_type"] != "student":
        raise HTTPException(400, "Invalid student ID")
    referral = create_referral(user["id"], student_id, urgency, notes)
    _safe_notify(student_id, "Referral Created", f"A counsellor has created a {urgency}-urgency referral for you.", "referral")
    write_audit(
        actor_id=user["id"], actor_role=user["role_type"],
        action="referral.create", target_type="referral", target_id=referral["id"],
        payload={"urgency": urgency, "student_id": student_id},
        ip=request.client.host if request.client else None,
    )
    return referral


@app.patch("/api/counsellor/referrals/{referral_id}")
async def update_counsellor_referral(referral_id: str, data: dict, request: Request, user: dict = Depends(require_auth)):
    if user["role_type"] not in ("counsellor", "admin"):
        raise HTTPException(403, "Counsellor or admin access required")
    status = data.get("status")
    notes = data.get("notes")
    if status and status not in ("open", "accepted", "completed", "declined"):
        raise HTTPException(400, "Invalid status")
    existing_rows = get_referrals()
    existing = next((r for r in existing_rows if r["id"] == referral_id), None)
    if not existing:
        raise HTTPException(404, "Referral not found")
    if existing["counsellor_id"] != user["id"] and user["role_type"] != "admin":
        raise HTTPException(403, "You do not own this referral")
    result = update_referral(referral_id, status=status, notes=notes)
    if not result:
        raise HTTPException(404, "Referral not found")
    if status and status != existing.get("status"):
        _safe_notify(existing["student_id"], "Referral Update", f"Your referral status has been updated to '{status}'.", "referral")
    write_audit(
        actor_id=user["id"], actor_role=user["role_type"],
        action="referral.update", target_type="referral", target_id=referral_id,
        payload={"status": status, "notes": notes},
        ip=request.client.host if request.client else None,
    )
    return result


# ── Communications routes ────────────────────────────────────────────

@app.get("/api/counsellor/conversations")
async def get_counsellor_conversations(user: dict = Depends(require_auth)):
    if user["role_type"] not in ("counsellor", "admin"):
        raise HTTPException(403, "Counsellor or admin access required")
    return get_conversations(user["id"])


@app.get("/api/counsellor/conversations/{other_id}")
async def get_counsellor_conversation(other_id: str, user: dict = Depends(require_auth)):
    if user["role_type"] not in ("counsellor", "admin"):
        raise HTTPException(403, "Counsellor or admin access required")
    mark_all_read(user["id"], other_id)
    return get_conversation(user["id"], other_id)


@app.post("/api/counsellor/messages")
async def send_counsellor_message(data: dict, user: dict = Depends(require_auth)):
    if user["role_type"] not in ("counsellor", "admin"):
        raise HTTPException(403, "Counsellor or admin access required")
    receiver_id = data.get("receiver_id")
    message = data.get("message", "").strip()
    if not receiver_id:
        raise HTTPException(400, "Receiver ID required")
    if not message:
        raise HTTPException(400, "Message cannot be empty")
    msg = send_message(user["id"], receiver_id, message)
    _safe_notify(receiver_id, "New Message", f"New message from {user['name']}", "general")
    return msg


# ── Dashboard ────────────────────────────────────────────────────────

@app.get("/api/counsellor/dashboard")
async def counsellor_dashboard(user: dict = Depends(require_auth)):
    if user["role_type"] not in ("counsellor", "admin"):
        raise HTTPException(403, "Counsellor or admin access required")
    return get_counsellor_dashboard(user["id"])


# ── Notifications routes ─────────────────────────────────────────────

@app.get("/api/notifications")
async def get_user_notifications(user: dict = Depends(require_auth)):
    return {
        "notifications": get_notifications(user["id"]),
        **get_notification_summary(user["id"]),
    }


@app.post("/api/notifications/read")
async def mark_user_notification_read(data: dict, user: dict = Depends(require_auth)):
    nid = data.get("id")
    if nid:
        mark_notification_read(nid)
    return {"ok": True}


# ── Admin routes ─────────────────────────────────────────────────────

@app.get("/api/admin/users")
async def admin_list_users(user: dict = Depends(require_auth)):
    if user["role_type"] != "admin":
        raise HTTPException(403, "Admin access required")
    return get_all_users()


@app.post("/api/admin/broadcast")
async def admin_broadcast(data: dict, request: Request, user: dict = Depends(require_auth)):
    if user["role_type"] != "admin":
        raise HTTPException(403, "Admin access required")
    title = (data.get("title") or "").strip()
    message = (data.get("message") or "").strip()
    target_role = data.get("target_role")  # None = all, or "student"/"counsellor"
    if not title or not message:
        raise HTTPException(400, "Title and message are required")
    users = get_all_users()
    if target_role:
        users = [u for u in users if u["role_type"] == target_role]
    sent = 0
    for u in users:
        if u["id"] != user["id"]:  # don't notify yourself
            _safe_notify(u["id"], title, message, "broadcast")
            sent += 1
    write_audit(
        actor_id=user["id"], actor_role=user["role_type"],
        action="broadcast.send", target_type="notification",
        payload={"title": title, "target_role": target_role, "recipients": sent},
        ip=request.client.host if request.client else None,
    )
    logger.info("Broadcast: admin=%s title=%r sent_to=%d", user["id"], title, sent)
    return {"ok": True, "sent": sent}


# ── User directory ──────────────────────────────────────────────────

@app.get("/api/users/directory")
async def get_user_directory(role: str | None = None, user: dict = Depends(require_auth)):
    """List users by role for starting conversations. Any authenticated user can call this."""
    users = get_all_users()
    if role:
        users = [u for u in users if u["role_type"] == role]
    return users


# ── Resources routes ─────────────────────────────────────────────────

@app.get("/api/resources")
async def get_resources(user: dict = Depends(require_auth)):
    return RESOURCES


@app.get("/api/resources/states")
async def get_state_resources(user: dict = Depends(require_auth)):
    return US_STATE_RESOURCES


@app.get("/api/resources/team")
async def get_team():
    return TEAM_MEMBERS


# ═════════════════════════════════════════════════════════════════════
# API v1 routes
# ═════════════════════════════════════════════════════════════════════

def _require_counsellor(user: dict) -> None:
    """Raise 403 if the authenticated user is not a counsellor or admin."""
    if user["role_type"] not in ("counsellor", "admin"):
        raise HTTPException(403, "Counsellor or admin access required")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ── Consent management ────────────────────────────────────────────────

@app.post("/api/v1/students/{student_id}/consent", status_code=201)
async def v1_create_and_dispatch_consent(
    student_id: str,
    data: dict,
    request: Request,
    user: dict = Depends(require_auth),
):
    _require_counsellor(user)
    student = get_user_by_id(student_id)
    if not student or student["role_type"] != "student":
        raise HTTPException(404, "Student not found")

    recipient_email = data.get("recipient_email", "").strip()
    if not recipient_email:
        raise HTTPException(400, "recipient_email is required")

    recipient_role = data.get("recipient_role", "student")
    if recipient_role not in ("student", "parent"):
        raise HTTPException(400, "recipient_role must be 'student' or 'parent'")

    platforms = data.get("platforms", [])
    mode = data.get("mode", "ON_DEMAND")
    if mode not in ("ON_DEMAND", "CONTINUOUS"):
        raise HTTPException(400, "mode must be 'ON_DEMAND' or 'CONTINUOUS'")

    try:
        consent = create_consent(
            student_id=student_id,
            counsellor_id=user["id"],
            recipient_email=recipient_email,
            recipient_role=recipient_role,
            platforms=platforms,
            mode=mode,
        )
        consent = dispatch_consent(consent["id"], actor_id=user["id"], ip=_client_ip(request))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("create_consent error: %s", exc)
        raise HTTPException(500, "Failed to create consent")

    write_audit(
        user["id"], user["role_type"], "CONSENT_CREATED",
        "consent", consent["id"],
        payload={"student_id": student_id, "recipient_email": recipient_email},
        ip=_client_ip(request),
    )
    _safe_notify(student_id, "Consent Request Sent",
                 "A consent request has been dispatched to your guardian/student.", "consent")
    return consent


@app.get("/api/v1/consents")
async def v1_list_consents(
    status: str | None = None,
    user: dict = Depends(require_auth),
):
    _require_counsellor(user)
    consents = get_consents_by_counsellor(user["id"])
    if status:
        consents = [c for c in consents if c["status"] == status.upper()]
    return {"consents": consents, "total": len(consents)}


@app.get("/api/v1/consents/{consent_id}")
async def v1_get_consent(
    consent_id: str,
    user: dict = Depends(require_auth),
):
    _require_counsellor(user)
    consent = get_consent_by_id(consent_id)
    if not consent:
        raise HTTPException(404, "Consent not found")
    if consent["counsellor_id"] != user["id"] and user["role_type"] != "admin":
        raise HTTPException(403, "Access denied")
    return consent


@app.post("/api/v1/consents/{consent_id}/dispatch")
async def v1_dispatch_consent(
    consent_id: str,
    request: Request,
    user: dict = Depends(require_auth),
):
    _require_counsellor(user)
    consent = get_consent_by_id(consent_id)
    if not consent:
        raise HTTPException(404, "Consent not found")
    if consent["counsellor_id"] != user["id"] and user["role_type"] != "admin":
        raise HTTPException(403, "Access denied")
    try:
        updated = dispatch_consent(consent_id, actor_id=user["id"], ip=_client_ip(request))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("dispatch_consent error: %s", exc)
        raise HTTPException(500, "Failed to dispatch consent")
    return updated


@app.post("/api/v1/consents/{consent_id}/remind")
async def v1_remind_consent(
    consent_id: str,
    request: Request,
    user: dict = Depends(require_auth),
):
    _require_counsellor(user)
    consent = get_consent_by_id(consent_id)
    if not consent:
        raise HTTPException(404, "Consent not found")
    if consent["counsellor_id"] != user["id"] and user["role_type"] != "admin":
        raise HTTPException(403, "Access denied")
    if consent["status"] not in ("PENDING", "VIEWED"):
        raise HTTPException(400, f"Cannot send reminder for consent in status {consent['status']}")
    write_audit(
        user["id"], user["role_type"], "CONSENT_REMINDER_SENT",
        "consent", consent_id,
        payload={"recipient": consent["recipient_email"]},
        ip=_client_ip(request),
    )
    return {"ok": True, "message": "Reminder recorded"}


@app.post("/api/v1/consents/{consent_id}/cancel")
async def v1_cancel_consent(
    consent_id: str,
    request: Request,
    user: dict = Depends(require_auth),
):
    _require_counsellor(user)
    consent = get_consent_by_id(consent_id)
    if not consent:
        raise HTTPException(404, "Consent not found")
    if consent["counsellor_id"] != user["id"] and user["role_type"] != "admin":
        raise HTTPException(403, "Access denied")
    if consent["status"] != "PENDING":
        raise HTTPException(400, f"Only PENDING consents can be cancelled (current: {consent['status']})")
    try:
        from backend.database import update_consent_status
        updated = update_consent_status(consent_id, "DRAFT")
    except Exception as exc:
        logger.error("cancel_consent error: %s", exc)
        raise HTTPException(500, "Failed to cancel consent")
    write_audit(
        user["id"], user["role_type"], "CONSENT_CANCELLED",
        "consent", consent_id, ip=_client_ip(request),
    )
    return updated


# ── Consent portal (magic-link, no JWT required) ──────────────────────

@app.get("/api/v1/portal/consents/{token}")
async def v1_portal_get_consent(token: str, request: Request):
    consent = get_consent_by_token(token)
    if not consent:
        raise HTTPException(404, "Consent not found or link invalid")
    # Validate magic token expiry
    expires = consent.get("magic_token_expires_at") or ""
    if expires and datetime.now(timezone.utc).isoformat() > expires:
        raise HTTPException(410, "This consent link has expired")
    if consent["status"] not in ("PENDING", "VIEWED", "ACCEPTED", "DECLINED"):
        raise HTTPException(410, "This consent link is no longer active")
    try:
        consent = record_view(consent["id"], ip=_client_ip(request))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("portal_get_consent error: %s", exc)
        raise HTTPException(500, "Failed to record view")
    # Strip sensitive fields before returning to unauthenticated recipients
    safe_keys = {
        "id", "student_id", "recipient_email", "recipient_role", "status",
        "platforms_json", "mode", "document_version", "dispatched_at",
        "viewed_at", "accepted_at", "declined_at", "expires_at", "created_at",
    }
    return {k: v for k, v in consent.items() if k in safe_keys}


@app.post("/api/v1/portal/consents/{token}/accept")
async def v1_portal_accept_consent(token: str, data: dict, request: Request):
    consent = get_consent_by_token(token)
    if not consent:
        raise HTTPException(404, "Consent not found or link invalid")
    expires = consent.get("magic_token_expires_at") or ""
    if expires and datetime.now(timezone.utc).isoformat() > expires:
        raise HTTPException(410, "This consent link has expired")

    signature_name = (data.get("signature_name") or "").strip()
    if not signature_name:
        raise HTTPException(400, "signature_name is required")
    platforms = data.get("platforms")

    try:
        updated = accept_consent(
            consent["id"],
            signature_name=signature_name,
            ip=_client_ip(request),
            platforms=platforms,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("portal_accept_consent error: %s", exc)
        raise HTTPException(500, "Failed to accept consent")
    return {"ok": True, "status": updated["status"]}


@app.post("/api/v1/portal/consents/{token}/decline")
async def v1_portal_decline_consent(token: str, request: Request):
    consent = get_consent_by_token(token)
    if not consent:
        raise HTTPException(404, "Consent not found or link invalid")
    expires = consent.get("magic_token_expires_at") or ""
    if expires and datetime.now(timezone.utc).isoformat() > expires:
        raise HTTPException(410, "This consent link has expired")
    try:
        updated = decline_consent(consent["id"], ip=_client_ip(request))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("portal_decline_consent error: %s", exc)
        raise HTTPException(500, "Failed to decline consent")
    return {"ok": True, "status": updated["status"]}


@app.post("/api/v1/portal/consents/{token}/revoke")
async def v1_portal_revoke_consent(token: str, request: Request):
    consent = get_consent_by_token(token)
    if not consent:
        raise HTTPException(404, "Consent not found or link invalid")
    try:
        updated = revoke_consent(consent["id"], ip=_client_ip(request))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("portal_revoke_consent error: %s", exc)
        raise HTTPException(500, "Failed to revoke consent")
    return {"ok": True, "status": updated["status"]}


# ── Account linking ───────────────────────────────────────────────────

@app.get("/api/v1/students/{student_id}/accounts")
async def v1_list_accounts(student_id: str, user: dict = Depends(require_auth)):
    _require_counsellor(user)
    student = get_user_by_id(student_id)
    if not student or student["role_type"] != "student":
        raise HTTPException(404, "Student not found")
    accounts = get_linked_accounts(student_id)
    return {"accounts": accounts, "total": len(accounts)}


@app.post("/api/v1/students/{student_id}/accounts", status_code=201)
async def v1_create_account(
    student_id: str,
    data: dict,
    request: Request,
    user: dict = Depends(require_auth),
):
    _require_counsellor(user)
    student = get_user_by_id(student_id)
    if not student or student["role_type"] != "student":
        raise HTTPException(404, "Student not found")

    platform = (data.get("platform") or "").strip().lower()
    if not platform:
        raise HTTPException(400, "platform is required")

    mode = data.get("mode", "handle")
    if mode not in ("oauth", "handle"):
        raise HTTPException(400, "mode must be 'oauth' or 'handle'")

    handle = (data.get("handle") or "").strip() or None
    consent_id = data.get("consent_id")

    try:
        account = create_linked_account(student_id, consent_id, platform, mode, handle)
    except Exception as exc:
        logger.error("create_linked_account error: %s", exc)
        raise HTTPException(500, "Failed to link account")

    write_audit(
        user["id"], user["role_type"], "ACCOUNT_LINKED",
        "linked_account", account["id"],
        payload={"student_id": student_id, "platform": platform},
        ip=_client_ip(request),
    )
    return account


@app.delete("/api/v1/students/{student_id}/accounts/{account_id}")
async def v1_delete_account(
    student_id: str,
    account_id: str,
    request: Request,
    user: dict = Depends(require_auth),
):
    _require_counsellor(user)
    student = get_user_by_id(student_id)
    if not student or student["role_type"] != "student":
        raise HTTPException(404, "Student not found")

    ok = revoke_linked_account(account_id)
    if not ok:
        raise HTTPException(404, "Linked account not found")

    write_audit(
        user["id"], user["role_type"], "ACCOUNT_REVOKED",
        "linked_account", account_id,
        payload={"student_id": student_id},
        ip=_client_ip(request),
    )
    return {"ok": True}


# ── Alert queue ───────────────────────────────────────────────────────

@app.get("/api/v1/alerts")
async def v1_list_alerts(
    status: str = "OPEN",
    user: dict = Depends(require_auth),
):
    _require_counsellor(user)
    valid_statuses = {"OPEN", "CLOSED"}
    filter_status = status.upper() if status.upper() in valid_statuses else None
    alerts = get_alerts(user["id"], status=filter_status)
    return {"alerts": alerts, "total": len(alerts)}


_VALID_DISPOSITIONS = {"REACH_OUT", "SCHEDULE_CHECKIN", "ESCALATE", "DISMISS"}


@app.post("/api/v1/alerts/{alert_id}/disposition")
async def v1_dispose_alert(
    alert_id: str,
    data: dict,
    request: Request,
    user: dict = Depends(require_auth),
):
    _require_counsellor(user)
    action = (data.get("action") or "").strip().upper()
    if action not in _VALID_DISPOSITIONS:
        raise HTTPException(400, f"action must be one of: {', '.join(sorted(_VALID_DISPOSITIONS))}")

    reason_code = (data.get("reason_code") or "").strip()
    reason_note = (data.get("reason_note") or "").strip()
    supersedes_id = data.get("supersedes_id")

    try:
        result = dispose_alert(
            alert_id=alert_id,
            disposition=action,
            reason_code=reason_code,
            reason_note=reason_note,
            dispositioned_by=user["id"],
            supersedes_id=supersedes_id,
        )
    except Exception as exc:
        logger.error("dispose_alert error: %s", exc)
        raise HTTPException(500, "Failed to dispose alert")

    if not result:
        raise HTTPException(404, "Alert not found")

    write_audit(
        user["id"], user["role_type"], "ALERT_DISPOSITIONED",
        "alert", alert_id,
        payload={"action": action, "reason_code": reason_code},
        ip=_client_ip(request),
    )
    return result


# ── Risk timeline ─────────────────────────────────────────────────────

@app.get("/api/v1/students/{student_id}/timeline")
async def v1_student_timeline(student_id: str, user: dict = Depends(require_auth)):
    _require_counsellor(user)
    student = get_user_by_id(student_id)
    if not student or student["role_type"] != "student":
        raise HTTPException(404, "Student not found")

    history = get_rolling_risk_history(student_id)
    alerts = get_alerts(user["id"], status=None)
    student_alerts = [a for a in alerts if a["student_id"] == student_id]

    return {
        "student_id": student_id,
        "student_name": student["name"],
        "rolling_risk_history": history,
        "alert_markers": [
            {
                "id": a["id"],
                "fired_at": a["fired_at"],
                "risk_score": a["risk_score"],
                "platform": a["platform"],
                "status": a["status"],
                "disposition": a["disposition"],
            }
            for a in student_alerts
        ],
    }


# ── Notes ─────────────────────────────────────────────────────────────

@app.get("/api/v1/students/{student_id}/notes")
async def v1_list_notes(student_id: str, user: dict = Depends(require_auth)):
    _require_counsellor(user)
    student = get_user_by_id(student_id)
    if not student or student["role_type"] != "student":
        raise HTTPException(404, "Student not found")
    notes = get_notes(student_id)
    return {"notes": notes, "total": len(notes)}


@app.post("/api/v1/students/{student_id}/notes", status_code=201)
async def v1_create_note(
    student_id: str,
    data: dict,
    request: Request,
    user: dict = Depends(require_auth),
):
    _require_counsellor(user)
    student = get_user_by_id(student_id)
    if not student or student["role_type"] != "student":
        raise HTTPException(404, "Student not found")

    body = (data.get("body") or "").strip()
    if not body:
        raise HTTPException(400, "Note body cannot be empty")

    try:
        note = create_note(student_id=student_id, author_id=user["id"], body=body)
    except Exception as exc:
        logger.error("create_note error: %s", exc)
        raise HTTPException(500, "Failed to create note")

    write_audit(
        user["id"], user["role_type"], "NOTE_CREATED",
        "note", note["id"],
        payload={"student_id": student_id},
        ip=_client_ip(request),
    )
    return note


# ── Audit log ─────────────────────────────────────────────────────────

@app.get("/api/v1/audit")
async def v1_audit_log(limit: int = 100, user: dict = Depends(require_auth)):
    _require_counsellor(user)
    if limit < 1 or limit > 1000:
        raise HTTPException(400, "limit must be between 1 and 1000")
    entries = get_audit_log(user["id"], limit=limit)
    return {"entries": entries, "total": len(entries)}


# ── Rolling risk trigger ──────────────────────────────────────────────

@app.post("/api/v1/students/{student_id}/analyze")
async def v1_student_analyze(
    student_id: str,
    data: dict,
    request: Request,
    user: dict = Depends(require_auth),
):
    _require_counsellor(user)
    student = get_user_by_id(student_id)
    if not student or student["role_type"] != "student":
        raise HTTPException(404, "Student not found")

    platform = (data.get("platform") or "unknown").strip().lower()
    posts = data.get("posts")
    if not isinstance(posts, list):
        raise HTTPException(400, "posts must be a list")
    if not posts:
        raise HTTPException(400, "posts list cannot be empty")

    for i, post in enumerate(posts):
        if not isinstance(post, dict):
            raise HTTPException(400, f"posts[{i}] must be an object")
        if "risk_score" not in post:
            raise HTTPException(400, f"posts[{i}] missing required field 'risk_score'")

    rolling_score = compute_rolling_risk(posts, window_days=14)
    top_platform = platform
    n_posts = len(posts)

    risk_record = update_rolling_risk(
        student_id=student_id,
        score=rolling_score,
        top_platform=top_platform,
        n_posts=n_posts,
    )

    write_audit(
        user["id"], user["role_type"], "ROLLING_RISK_COMPUTED",
        "student", student_id,
        payload={"platform": platform, "score": rolling_score, "n_posts": n_posts},
        ip=_client_ip(request),
    )

    alert = None
    if rolling_score >= 0.65:
        try:
            alert = try_create_alert(
                student_id=student_id,
                counsellor_id=user["id"],
                rolling_score=rolling_score,
                platform=platform,
            )
        except Exception as exc:
            logger.error("try_create_alert error student=%s: %s", student_id, exc)

        if alert:
            _safe_notify(
                user["id"],
                "Risk Alert Triggered",
                f"Student {student['name']} has a rolling risk score of {rolling_score:.2f} on {platform}.",
                "alert",
            )
            write_audit(
                user["id"], user["role_type"], "ALERT_CREATED",
                "alert", alert["id"],
                payload={"student_id": student_id, "score": rolling_score},
                ip=_client_ip(request),
            )

    return {
        "student_id": student_id,
        "platform": platform,
        "rolling_score": rolling_score,
        "n_posts": n_posts,
        "risk_record": risk_record,
        "alert_created": alert is not None,
        "alert": alert,
    }


# ═════════════════════════════════════════════════════════════════════
# Group routes (counsellor-only)
# ═════════════════════════════════════════════════════════════════════


@app.get("/api/v1/groups")
async def v1_list_groups(user: dict = Depends(require_auth)):
    if user["role_type"] not in ("counsellor", "admin"):
        raise HTTPException(403, "Counsellor or admin access required")
    groups = get_groups_for_user(user["id"])
    result = []
    for g in groups:
        unread = get_group_unread_count(g["id"], user["id"])
        result.append({
            "id": g["id"],
            "name": g["name"],
            "description": g["description"],
            "avatar_url": g["avatar_url"],
            "created_by": g["created_by"],
            "is_active": bool(g["is_active"]),
            "member_count": g["member_count"],
            "unread_count": unread,
            "created_at": g["created_at"],
            "updated_at": g["updated_at"],
        })
    return {"groups": result, "total": len(result)}


@app.post("/api/v1/groups", status_code=201)
async def v1_create_group(req: CreateGroupRequest, user: dict = Depends(require_auth)):
    if user["role_type"] not in ("counsellor", "admin"):
        raise HTTPException(403, "Counsellor or admin access required")
    try:
        group = create_group(req.name, req.description, user["id"])
        add_group_member(group["id"], user["id"], role="admin")
        for mid in req.member_ids:
            member_user = get_user_by_id(mid)
            if member_user and member_user["role_type"] == "student":
                add_group_member(group["id"], mid, role="member")
                _safe_notify(mid, "Group Invitation",
                             f"You have been added to the group '{req.name}' by {user['name']}.",
                             "system")
        members = get_group_members(group["id"])
        return {
            **group,
            "is_active": True,
            "member_count": len(members),
            "members": [{
                "id": m["id"], "user_id": m["user_id"],
                "name": m["name"], "email": m["email"],
                "role": m["role"], "joined_at": m["joined_at"],
            } for m in members],
        }
    except Exception as exc:
        logger.error("create_group error: %s", exc)
        raise HTTPException(500, "Failed to create group")


@app.get("/api/v1/groups/{group_id}")
async def v1_get_group(group_id: str, user: dict = Depends(require_auth)):
    if user["role_type"] not in ("counsellor", "admin"):
        raise HTTPException(403, "Counsellor or admin access required")
    group = get_group_by_id(group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    if not is_group_member(group_id, user["id"]):
        raise HTTPException(403, "You are not a member of this group")
    members = get_group_members(group_id)
    return {
        **group,
        "is_active": bool(group["is_active"]),
        "member_count": len(members),
        "members": [{
            "id": m["id"], "user_id": m["user_id"],
            "name": m["name"], "email": m["email"],
            "role": m["role"], "joined_at": m["joined_at"],
        } for m in members],
    }


@app.patch("/api/v1/groups/{group_id}")
async def v1_update_group(group_id: str, req: UpdateGroupRequest, user: dict = Depends(require_auth)):
    if user["role_type"] not in ("counsellor", "admin"):
        raise HTTPException(403, "Counsellor or admin access required")
    group = get_group_by_id(group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    if group["created_by"] != user["id"] and user["role_type"] != "admin":
        raise HTTPException(403, "Only the group creator can update this group")
    updated = update_group(group_id, name=req.name, description=req.description)
    if not updated:
        raise HTTPException(404, "Group not found")
    return {**updated, "is_active": bool(updated["is_active"])}


@app.delete("/api/v1/groups/{group_id}")
async def v1_delete_group(group_id: str, user: dict = Depends(require_auth)):
    if user["role_type"] not in ("counsellor", "admin"):
        raise HTTPException(403, "Counsellor or admin access required")
    group = get_group_by_id(group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    if group["created_by"] != user["id"] and user["role_type"] != "admin":
        raise HTTPException(403, "Only the group creator can delete this group")
    ok = delete_group(group_id)
    if not ok:
        raise HTTPException(404, "Group not found")
    return {"ok": True}


@app.post("/api/v1/groups/{group_id}/members", status_code=201)
async def v1_add_group_members(group_id: str, data: dict, user: dict = Depends(require_auth)):
    if user["role_type"] not in ("counsellor", "admin"):
        raise HTTPException(403, "Counsellor or admin access required")
    group = get_group_by_id(group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    if not is_group_member(group_id, user["id"]):
        raise HTTPException(403, "You are not a member of this group")
    user_ids = data.get("user_ids", [])
    if not isinstance(user_ids, list) or not user_ids:
        raise HTTPException(400, "user_ids must be a non-empty list")
    added = []
    for uid in user_ids:
        member_user = get_user_by_id(uid)
        if member_user and member_user["role_type"] == "student":
            result = add_group_member(group_id, uid, role="member")
            if result:
                added.append(result)
                _safe_notify(uid, "Group Invitation",
                             f"You have been added to the group '{group['name']}' by {user['name']}.",
                             "system")
    return {"added": len(added), "members": added}


@app.delete("/api/v1/groups/{group_id}/members/{user_id}")
async def v1_remove_group_member(group_id: str, user_id: str, user: dict = Depends(require_auth)):
    if user["role_type"] not in ("counsellor", "admin"):
        raise HTTPException(403, "Counsellor or admin access required")
    group = get_group_by_id(group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    if not is_group_member(group_id, user["id"]) and user["role_type"] != "admin":
        raise HTTPException(403, "You are not a member of this group")
    if user_id == group["created_by"] and user["role_type"] != "admin":
        raise HTTPException(400, "Cannot remove the group creator")
    ok = remove_group_member(group_id, user_id)
    if not ok:
        raise HTTPException(404, "Member not found")
    return {"ok": True}


@app.get("/api/v1/groups/{group_id}/messages")
async def v1_get_group_messages(
    group_id: str,
    limit: int = 50,
    before_id: str | None = None,
    user: dict = Depends(require_auth),
):
    group = get_group_by_id(group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    if not is_group_member(group_id, user["id"]):
        raise HTTPException(403, "You are not a member of this group")
    messages = get_group_messages(group_id, limit=limit, before_id=before_id)
    return {"messages": messages, "total": len(messages)}


@app.post("/api/v1/groups/{group_id}/messages", status_code=201)
async def v1_send_group_message(
    group_id: str,
    req: GroupMessageRequest,
    request: Request,
    user: dict = Depends(require_auth),
):
    group = get_group_by_id(group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    if not is_group_member(group_id, user["id"]):
        raise HTTPException(403, "You are not a member of this group")
    msg = send_group_message(group_id, user["id"], req.message)
    # Notify other group members
    members = get_group_members(group_id)
    for m in members:
        if m["user_id"] != user["id"] and should_notify(m["user_id"], "group_message", group_id):
            _safe_notify(m["user_id"], f"Group: {group['name']}",
                         f"{user['name']}: {req.message[:120]}{'...' if len(req.message) > 120 else ''}",
                         "group_message")
    msg["sender_name"] = user["name"]
    return msg


@app.post("/api/v1/groups/{group_id}/read")
async def v1_mark_group_read(group_id: str, user: dict = Depends(require_auth)):
    if not is_group_member(group_id, user["id"]):
        raise HTTPException(403, "You are not a member of this group")
    mark_all_group_messages_read(group_id, user["id"])
    return {"ok": True}


# ═════════════════════════════════════════════════════════════════════
# General messaging routes (any authenticated user)
# ═════════════════════════════════════════════════════════════════════


@app.get("/api/messages/conversations")
async def get_my_conversations(user: dict = Depends(require_auth)):
    conversations = get_conversations(user["id"])
    # Also fetch group previews
    groups = get_groups_for_user(user["id"])
    group_previews = []
    for g in groups:
        msgs = get_group_messages(g["id"], limit=1)
        last_msg = msgs[-1] if msgs else None
        unread = get_group_unread_count(g["id"], user["id"])
        group_previews.append({
            "type": "group",
            "group_id": g["id"],
            "name": g["name"],
            "avatar_url": g.get("avatar_url", ""),
            "member_count": g["member_count"],
            "last_message": last_msg["message"] if last_msg else "",
            "last_time": last_msg["created_at"] if last_msg else "",
            "last_sender": last_msg["sender_name"] if last_msg else "",
            "unread": unread,
        })
    return {"direct": conversations, "groups": group_previews}


@app.post("/api/messages/send")
async def send_message_any(data: dict, user: dict = Depends(require_auth)):
    receiver_id = data.get("receiver_id")
    message = data.get("message", "").strip()
    if not receiver_id:
        raise HTTPException(400, "Receiver ID required")
    if not message:
        raise HTTPException(400, "Message cannot be empty")
    receiver = get_user_by_id(receiver_id)
    if not receiver:
        raise HTTPException(404, "Recipient not found")
    msg = send_message(user["id"], receiver_id, message)
    if should_notify(receiver_id, "message"):
        _safe_notify(receiver_id, "New Message", f"New message from {user['name']}", "message")
    return msg


@app.get("/api/messages/conversations/{other_id}")
async def get_conversation_any(other_id: str, user: dict = Depends(require_auth)):
    mark_all_read(user["id"], other_id)
    return get_conversation(user["id"], other_id)


@app.post("/api/messages/read")
async def mark_message_read(data: dict, user: dict = Depends(require_auth)):
    message_id = data.get("message_id")
    if message_id:
        mark_read(message_id)
    return {"ok": True}


@app.post("/api/messages/read-all/{other_id}")
async def mark_all_read_with(other_id: str, user: dict = Depends(require_auth)):
    mark_all_read(user["id"], other_id)
    return {"ok": True}


# ═════════════════════════════════════════════════════════════════════
# Notification preference routes
# ═════════════════════════════════════════════════════════════════════


@app.get("/api/notifications/preferences")
async def get_my_notification_preferences(user: dict = Depends(require_auth)):
    prefs = get_notification_preferences(user["id"])
    return {"preferences": prefs}


@app.put("/api/notifications/preferences/mute-group")
async def toggle_group_mute(req: MuteGroupRequest, user: dict = Depends(require_auth)):
    prefs = get_notification_preferences(user["id"])
    group_pref = next((p for p in prefs if p["type"] == "group_message"), None)
    muted = list(group_pref["muted_groups"]) if group_pref else []
    if req.muted and req.group_id not in muted:
        muted.append(req.group_id)
    elif not req.muted and req.group_id in muted:
        muted.remove(req.group_id)
    set_notification_preference(user["id"], "group_message", muted_groups=muted)
    return {"muted_groups": muted}


@app.put("/api/notifications/preferences/{notify_type}")
async def update_notification_preference(
    notify_type: str,
    req: UpdateNotificationPreferenceRequest,
    user: dict = Depends(require_auth),
):
    if notify_type not in NOTIFICATION_TYPES:
        raise HTTPException(400, f"Invalid notification type. Must be one of: {', '.join(sorted(NOTIFICATION_TYPES))}")
    pref = set_notification_preference(
        user["id"], notify_type,
        enabled=req.enabled,
        muted_groups=req.muted_groups,
    )
    return pref


@app.get("/api/config")
async def get_frontend_config():
    return {
        "supabase_url": SUPABASE_URL or "",
        "supabase_anon_key": SUPABASE_ANON_KEY or "",
    }


_frontend_dir = os.getenv("FRONTEND_DIR", "")
if _frontend_dir and Path(_frontend_dir).is_dir():
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
    logger.info("Serving frontend from %s", _frontend_dir)

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    reload = os.getenv("API_RELOAD", "false").lower() == "true"
    uvicorn.run("backend.main:app", host=host, port=port, reload=reload)
