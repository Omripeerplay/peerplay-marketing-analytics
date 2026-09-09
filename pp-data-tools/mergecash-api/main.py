"""
MergeCash API — FastAPI backend for the internal offerwall.

v4.1: Final security hardening.
- Single milestone per segment, per-segment time limits
- Timer from LiveOps popup first impression (anti-reset: checks ALL popup records)
- Firestore transactions for reward creation (no double-rewards)
- Fraud re-check at BOTH completion paths (check-progress + scheduler)
- 10-min player cache TTL (reduced from 1h)
- Idempotent notifications (notified flag in transaction)
- Rate limiting on all endpoints (login tightened to 5/min)
- Uniform error messages (no enumeration)
- Security event logging
- Request body size limit
- Email verification tracking (admin sees UNVERIFIED flag)
- No docs/openapi in production
"""

import os
import sys
import uuid
import json
import re
import logging
import random
import string
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone, date
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, EmailStr, field_validator
from google.cloud import bigquery, firestore
from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token as google_id_token

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.config import get_secret

import requests as http_requests
import jwt as pyjwt

# ── Config ──────────────────────────────────────────────────────────
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "yotam-395120")
BQ_DATASET = "peerplay"
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_DAYS = 30
SLACK_REWARDS_WEBHOOK = os.getenv("MERGECASH_SLACK_WEBHOOK", "")
# Bot-token path (preferred): post to #mergecash-rewards via chat.postMessage.
# Reuses the shared aso_copilot bot token; display name overridden to "MergeCash".
SLACK_BOT_TOKEN = os.getenv("MERGECASH_SLACK_BOT_TOKEN", "")
SLACK_REWARDS_CHANNEL = os.getenv("MERGECASH_SLACK_CHANNEL", "")
# Health monitor: DMs the alert user on problems. Uses slack-bot-token (support_ticket_invest bot,
# which has im:write to DM) — the aso bot used for reward alerts lacks im:write.
MONITOR_BOT_TOKEN = os.getenv("MERGECASH_MONITOR_BOT_TOKEN", "")
ALERT_USER = os.getenv("MERGECASH_ALERT_USER", "")
MAX_SIGNUPS_PER_IP_PER_DAY = 3
INTERNAL_SECRET = os.getenv("MERGECASH_INTERNAL_SECRET", "")
# Cloud Scheduler OIDC identity for the /api/internal/* jobs. When set, a Google-signed id_token
# from this SA authenticates the job instead of a static bearer secret — so no shared secret sits
# in the scheduler job config (where `gcloud scheduler jobs describe` and deploy.sh output both
# exposed it, twice into transcripts on 2026-08-03/04).
SCHEDULER_SA = os.getenv("MERGECASH_SCHEDULER_SA", "")
OIDC_AUDIENCE = os.getenv("MERGECASH_OIDC_AUDIENCE", "")
ALLOWED_ORIGINS = os.getenv(
    "MERGECASH_ALLOWED_ORIGINS",
    "https://mergecash-web.yotam.internal.peerplay.dev"
).split(",")

DEFAULT_OFFER_WINDOW_DAYS = int(os.getenv("MERGECASH_OFFER_WINDOW_DAYS", "7"))
LIVEOPS_POPUP_TABLE = "mergecash_liveops_popups"
MAX_REQUEST_BODY_BYTES = 102400  # 100KB

# Test whitelist — skip fraud check for internal testing. REMOVE BEFORE PRODUCTION LAUNCH.
TEST_WHITELIST = {
    "68a3a7393c411aab8978b1fb",  # Omri
    "68ff86c3d121e1f31b983c0e",  # Talor
    "689cb87bcc4760260bc92b62",  # Itai
    "6784e759033b01ce0bdc7abf",  # Dean
    "685c0e4af83c93e8c549219a",  # Dotan
    "68ab535ac13a96ae38d82b98",  # Maya
    "69dd06023d32c16d3e9a7c93",  # Yotam
    "67dd9eba5f53c6244f395721",  # Guy
    "68fe02350f758c7a17eddbad",  # Nati
    "697b03de8d5ae7bccef07359",  # Gal
}

# Help Scout (secrets via env vars only)
HELPSCOUT_APP_ID = os.getenv("HELPSCOUT_APP_ID", "")
HELPSCOUT_APP_SECRET = os.getenv("HELPSCOUT_APP_SECRET", "")
HELPSCOUT_MAILBOX_ID = int(os.getenv("HELPSCOUT_MAILBOX_ID", "0") or "0")

# ── Startup validation ─────────────────────────────────────────────
IS_PRODUCTION = os.getenv("CLOUD_RUN", "") == "true"
JWT_SECRET = os.getenv("MERGECASH_JWT_SECRET", "")
RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET", "")

if IS_PRODUCTION and (not JWT_SECRET or len(JWT_SECRET) < 16):
    raise RuntimeError("MERGECASH_JWT_SECRET not set or too short (min 16 chars). Cannot start in production.")

# WHY fail closed (added 2026-08-04): RECAPTCHA_SECRET was silently EMPTY in production from launch
# until 2026-08-04 — the secret `mergecash-recaptcha-secret` did not exist and deploy.sh masks that
# with `|| echo ''` (and the script has no `set -e`). Because BOTH call sites are written
# `if recaptcha_secret:` (see signup ~line 757 and contact ~line 1139), verification was skipped
# ENTIRELY rather than failing: real players solved the widget — the client refuses to submit without
# a token — while the server discarded the answer, and anything POSTing straight to /api/signup with a
# junk token walked right through. Refusing to boot converts that silent, invisible downgrade into a
# loud, unmissable failure. Safe by design: a non-starting revision never receives traffic, so Cloud
# Run keeps serving the previous healthy revision and the DEPLOY fails instead of the service.
if IS_PRODUCTION and not RECAPTCHA_SECRET_KEY:
    raise RuntimeError(
        "RECAPTCHA_SECRET not set. Cannot start in production — CAPTCHA verification would be "
        "silently skipped (both call sites are `if recaptcha_secret:`). Check Secret Manager secret "
        "`mergecash-recaptcha-secret` is readable by the runtime service account.")

def get_jwt_secret():
    return JWT_SECRET

def get_recaptcha_secret():
    return RECAPTCHA_SECRET_KEY


# ── reCAPTCHA solve-origin allow-list ──────────────────────────────
# WHY: siteverify returns the `hostname` the CAPTCHA was solved on, and until now we only read
# `success` and threw that field away. Google only issues tokens for domains registered on the site
# key, so this was not open to the whole internet — but it means a token solved on ANY domain on that
# key is accepted by production, and the key is edited in a console with no review and no audit trail
# reaching this repo. Registering one dev/staging domain would therefore silently widen production
# auth. Checking the hostname here makes the API's trust boundary explicit in code instead of implicit
# in someone's console session.
# Current key (v2 Checkbox "MergeCash") has exactly these two domains registered:
RECAPTCHA_ALLOWED_HOSTNAMES = {
    h.strip().lower()
    for h in os.getenv(
        "RECAPTCHA_ALLOWED_HOSTNAMES",
        "mergecash.peerplay.com,mergecash-web.yotam.internal.peerplay.dev",
    ).split(",")
    if h.strip()
}

# WHY log_only by DEFAULT (shadow-first): if the hostname Google actually returns differs from what we
# expect here — a trailing dot, a www prefix, an absent field on some widget config — enforcing
# immediately would reject EVERY signup and contact submission, turning a hardening change into a
# total outage of the funnel. So we observe first: log the real values against live traffic, confirm
# them, then set RECAPTCHA_HOSTNAME_MODE=enforce. Same reasoning as the auth-transport rule: never
# change a credential path and its enforcement in the same deploy.
RECAPTCHA_HOSTNAME_MODE = os.getenv("RECAPTCHA_HOSTNAME_MODE", "log_only").strip().lower()


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mergecash-api")


def captcha_hostname_ok(captcha_result: dict, source: str) -> bool:
    """True if the CAPTCHA solve origin is acceptable.

    Returns True in log_only mode even for an unexpected hostname — the event is still recorded, so
    `captcha_hostname_unexpected` in mergecash_events is what tells you whether it is safe to flip
    RECAPTCHA_HOSTNAME_MODE to enforce. Zero of those events over a full offer means enforce is safe.
    """
    hostname = (captcha_result.get("hostname") or "").strip().lower()
    if hostname and hostname in RECAPTCHA_ALLOWED_HOSTNAMES:
        return True
    log_event("captcha_hostname_unexpected", properties={
        "hostname": hostname or "(absent)",
        "source": source,
        "mode": RECAPTCHA_HOSTNAME_MODE,
    })
    logger.warning(
        "CAPTCHA solved on unexpected hostname %r (source=%s, mode=%s, allowed=%s)",
        hostname or "(absent)", source, RECAPTCHA_HOSTNAME_MODE,
        sorted(RECAPTCHA_ALLOWED_HOSTNAMES),
    )
    return RECAPTCHA_HOSTNAME_MODE != "enforce"

app = FastAPI(
    title="MergeCash API",
    version="4.1.0",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None,
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)


# ── Request body size limit middleware ─────────────────────────────

class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > MAX_REQUEST_BODY_BYTES:
                return JSONResponse(status_code=413, content={"detail": "Request body too large"})
        return await call_next(request)

app.add_middleware(BodySizeLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-MergeCash-Token"],
)


# ── In-memory rate limiter ─────────────────────────────────────────
_rate_limits: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(key: str, max_requests: int, window_seconds: int):
    """Raise 429 if key exceeded max_requests in the last window_seconds."""
    now = time.monotonic()
    cutoff = now - window_seconds
    hits = _rate_limits[key]
    _rate_limits[key] = [t for t in hits if t > cutoff]
    if len(_rate_limits[key]) >= max_requests:
        log_event("rate_limit_hit", properties={"key": key, "limit": max_requests, "window": window_seconds})
        raise HTTPException(429, "Too many requests. Please try again later.")
    _rate_limits[key].append(now)


def get_client_ip(request: Request) -> str:
    return request.headers.get("X-Forwarded-For", request.client.host or "unknown").split(",")[0].strip()


def normalize_email(email: str) -> str:
    """Normalize email: lowercase, strip gmail dots/plus aliases."""
    email = email.strip().lower()
    local, domain = email.rsplit("@", 1)
    if domain in ("gmail.com", "googlemail.com"):
        local = local.split("+")[0].replace(".", "")
    return f"{local}@{domain}"


# ── Database clients ────────────────────────────────────────────────

_fs_client = None
_bq_client = None


def get_fs():
    global _fs_client
    if _fs_client is None:
        _fs_client = firestore.Client(project=PROJECT_ID)
    return _fs_client


def get_bq():
    global _bq_client
    if _bq_client is None:
        import google.auth
        from google.auth.transport.requests import Request as AuthRequest
        credentials, project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform", "https://www.googleapis.com/auth/bigquery"]
        )
        credentials.refresh(AuthRequest())
        _bq_client = bigquery.Client(credentials=credentials, project=project or PROJECT_ID)
    return _bq_client


def T(name: str) -> str:
    return f"`{PROJECT_ID}.{BQ_DATASET}.{name}`"


def bq_param(name, typ, value):
    return bigquery.ScalarQueryParameter(name, typ, value)


def bq_query(sql, params=None):
    config = bigquery.QueryJobConfig(query_parameters=params or [])
    return get_bq().query(sql, job_config=config).result()


# ── Input validation ────────────────────────────────────────────────
HEX24 = re.compile(r'^[a-f0-9]{24}$', re.IGNORECASE)
LIVEOPS_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_\-]{1,256}$')


def validate_player_id(pid: str) -> str:
    pid = pid.strip()
    if not HEX24.match(pid):
        raise HTTPException(400, "Player ID must be a 24-character hex string")
    return pid


def validate_liveops_id(lid: str) -> str:
    """Validate liveops_id format: alphanumeric + dash/underscore, max 256 chars."""
    if not lid:
        return ""
    lid = lid.strip()
    if not LIVEOPS_ID_PATTERN.match(lid):
        return ""  # Silently ignore invalid liveops_id rather than error
    return lid


# ── JWT helpers ─────────────────────────────────────────────────────

def create_token(user_id: str) -> str:
    """Create JWT with minimal claims — no PII in token."""
    return pyjwt.encode(
        {
            "sub": user_id,
            "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY_DAYS),
            "iat": datetime.now(timezone.utc),
        },
        get_jwt_secret(), algorithm=JWT_ALGORITHM
    )


def decode_token(token: str) -> dict:
    try:
        return pyjwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")


def get_current_user(request: Request) -> dict:
    """Extract and validate user token. Checks header, query param, cookie."""
    token = request.headers.get("X-MergeCash-Token", "")
    source = "header"
    if not token:
        token = request.query_params.get("_token", "")
        source = "query"
    if not token:
        token = request.cookies.get("mc_token", "")
        source = "cookie"
    if not token:
        log_event("auth_failed", properties={"reason": "missing_token", "ip": get_client_ip(request)})
        raise HTTPException(401, "Missing token")
    user = decode_token(token)

    # READINESS PROBE for retiring the `?_token=` query param (which puts a live 30-day player token
    # into Cloud Run request logs — 397 distinct tokens in 7d, and log retention == token lifetime).
    # 100% of successful requests currently authenticate by QUERY PARAM, so the cookie leg has never
    # been exercised by a real client: dropping the param blind would sign out anyone whose cookie
    # isn't set. This logs, per request, whether a VALID cookie was ALSO present and resolves to the
    # same user — i.e. whether the param can be removed safely. Booleans only, never a token.
    # Remove this probe once the param is gone.
    try:
        ck = request.cookies.get("mc_token", "")
        cookie_ok = False
        if ck:
            try:
                cookie_ok = decode_token(ck).get("sub") == user.get("sub")
            except Exception:
                cookie_ok = False
        logger.info(f"auth_source_probe: source={source} cookie_present={bool(ck)} "
                    f"cookie_valid_same_user={cookie_ok} path={request.url.path}")
    except Exception:
        pass  # a probe must never break authentication
    return user


# ── Segment matching ───────────────────────────────────────────────
# Supports two modes:
#   Option B (primary): Per-player assignment from BQ table mergecash_player_assignments
#   Option A (fallback): Chapter-range rules from Firestore segments collection

PLAYER_ASSIGNMENTS_TABLE = "mergecash_player_assignments"


# ── Segment assignment logic (Itai's spec) ────────────────────────
# Buckets: 10-chapter bands, target 15 chapters ahead, with bump rule for edge players

SEGMENT_BUCKETS = [
    # (lo, hi, target_chapter, segment_id, reward_amount)
    (50, 59, 65, "50_to_65", 10),
    (60, 69, 75, "60_to_75", 20),
    (70, 79, 85, "70_to_85", 20),
    (80, 89, 95, "80_to_95", 20),
    (90, 99, 105, "90_to_105", 30),
    (100, 109, 115, "100_to_115", 30),
    (110, 119, 125, "110_to_125", 40),
    (120, 129, 135, "120_to_135", 50),
]


def assign_segment(current_chapter: int) -> Optional[dict]:
    """Assign segment based on live chapter using Itai's bucket + bump logic.
    Returns dict with segment_id, target_chapter, reward_amount, time_limit_days
    or None if chapter < 50 or >= 130 (not eligible)."""
    for i, (lo, hi, target, seg_id, reward) in enumerate(SEGMENT_BUCKETS):
        if lo <= current_chapter <= hi:
            # Bump rule: if in last 3 chapters of bucket, move to next bucket
            is_edge = current_chapter >= hi - 2
            if is_edge and i + 1 < len(SEGMENT_BUCKETS):
                _, _, n_target, n_seg_id, n_reward = SEGMENT_BUCKETS[i + 1]
                return {"segment_id": n_seg_id, "target_chapter": n_target, "reward_amount": float(n_reward), "time_limit_days": 7}
            return {"segment_id": seg_id, "target_chapter": target, "reward_amount": float(reward), "time_limit_days": 7}
    return None  # chapter < 50 or >= 130 → not eligible


# ── MergeCoins — real personal ladder (chapter 50-129 tier) ─────────────────────
# Two-threshold personal offer: target = signup chapter + 15 (Itai's spec, 2026-09-08), checkpoint =
# signup chapter + 11 (~73% of the trail). Both auto-pay — see check_progress/verify_all_progress.
# No player-facing "cash out" action anywhere; whichever threshold is actually crossed by window
# close is paid automatically. Below-50 and above-129 reward tiers are still pending Itai's numbers
# (2026-09-09 ask) — check_mergecoins_eligibility() only qualifies chapter 50-129 for now (the real
# range of SEGMENT_BUCKETS below — its last band tops out at 129, same boundary assign_segment() has
# always used), so anyone outside that range falls through to the original Offer-1-style path below,
# unchanged.
MERGECOINS_WINDOW_DAYS = 14          # Approved decision #1, 2026-09-06
MERGECOINS_CHECKPOINT_OFFSET = 11    # chapters from signup — Itai's spec, 2026-09-08
MERGECOINS_TARGET_OFFSET = 15        # chapters from signup — Itai's spec, personal/dynamic target
MERGECOINS_CHECKPOINT_PCT = 0.54     # fraction of the segment reward paid at the checkpoint
MERGECOINS_MAX_DAYS_LEFT_IN_WINDOW = 5   # eligible once <=this many days remain (incl. already past)
MERGECOINS_MIN_RECENT_ACTIVITY_DAYS = 7  # must have played within this many days to be eligible

# Per-partner offerwall attribution windows (days) — mirrored from
# dashboards/marketing-dashboard/app.py's OW_ATTRIBUTION_WINDOWS, the table already used for real
# ROAS reconciliation. WHY duplicated rather than imported: the dashboard is a separate deployable
# (Streamlit app), not a shared library — keep both in sync by hand if either changes. Resolves
# decision #5 (prime 30 vs 60 day) precisely: each source gets its OWN real window instead of one
# guessed global number.
OW_ATTRIBUTION_WINDOWS = {
    "exmox": 90, "adjoe": 90, "taurusx": 90, "cashcow": 60,
    "almedia": 90, "prodege": 30, "prime": 60, "kashkick": 60,
    "fluent": 90, "pinchme": 90, "torox.io": 30, "buff": 30,
    "tyrads": 30, "tyrads new": 30, "benjamin": 60, "brown boots": 60,
    "blindferret": 90, "bku": 30, "scrambly": 30, "prograd": 60,
    "vybs": 30, "payback": 90, "app samurai": 60, "ayet-studios": 30,
    "maf": 30, "mega fortuna": 30, "mistplay": 45, "playvault": 30,
    "playback rewards": 60, "adwake rewards": 60, "versemedia": 60,
}
# WHY almedia is special-cased: its window changed 60d -> 90d on 2026-07-16 (OW_WINDOW_TIMELINE in
# the dashboard). Installs before the change keep the window that was actually in force at the time.
_ALMEDIA_WINDOW_CHANGE_DATE = date(2026, 7, 16)
_ALMEDIA_PRE_CHANGE_WINDOW_DAYS = 60

# Test-only allowlist: bypasses ONLY the audience-eligibility gate below (offerwall source,
# attribution window, recent activity, chapter range) so a real, very-advanced test account (chapter
# 141, above the 50-129 tier being built) can still exercise the REAL target/checkpoint/payout logic
# end-to-end. Uses the top reward band ($50) since there's no real above-129 tier yet. Empty by
# default, so this can never affect anyone unless a player_id is explicitly added at deploy time.
# Delete once a real 130+ tier ships and this account is genuinely eligible on its own.
MERGECOINS_TEST_PLAYER_IDS = {
    p.strip() for p in os.getenv("MERGECOINS_TEST_PLAYER_IDS", "").split(",") if p.strip()
}


def mergecoins_segment_reward(current_chapter: int) -> Optional[dict]:
    """Strict chapter-band lookup for the MergeCoins reward segment/$ amount — no bump-for-staleness
    adjustment. WHY not reuse assign_segment(): that function's bump rule (move a near-the-edge
    player into the NEXT band's target) existed only to correct for the OLD fixed-per-bucket target
    being unfairly close for edge players. MergeCoins targets are personal (+15 from wherever they
    are), so there's no "unfairly close" case left to correct — verified against Itai's real
    assignment sheet (2026-09-08): a player at chapter 59 (edge of the 50-59 band) was assigned
    segment_id=50_to_65 / $10, NOT bumped to 60_to_75 / $20 the way assign_segment() would have.
    Returns None outside 50-129 (below-50/above-129 tiers pending Itai's numbers)."""
    for lo, hi, _old_target, seg_id, reward in SEGMENT_BUCKETS:
        if lo <= current_chapter <= hi:
            return {"segment_id": seg_id, "reward_amount": float(reward)}
    return None


def check_mergecoins_eligibility(player_id: str) -> Optional[dict]:
    """Real-time MergeCoins targeting: offerwall-attributed, <=N days left in their OWN partner's
    attribution window (or already past it), active within the last M days, not fraud-flagged.
    Chapter-range gating happens separately in match_segment() via mergecoins_segment_reward(), so
    this function only answers "is this player's timing/source/activity right", not "do we have a
    reward band for them". Returns None (never raises) on any failure or non-match — eligibility
    failing here must never block the existing Offer-1-style fallback path in match_segment().
    Cached in Firestore like validate_and_get_player, since it hits dim_player on every miss and
    eligibility doesn't meaningfully change within a 10-min window."""
    fs = get_fs()
    cache_ref = fs.collection("mergecoins_eligibility_cache").document(player_id)
    cache_doc = cache_ref.get()
    if cache_doc.exists:
        cached = cache_doc.to_dict()
        cache_age = (datetime.now(timezone.utc) - cached["cached_at"]).total_seconds()
        if cache_age < 600:
            return cached.get("result")

    result = None
    try:
        rows = bq_query(f"""
            WITH player AS (
                SELECT LOWER(first_mediasource) AS source, install_date, last_event_time
                FROM {T('dim_player')}
                WHERE distinct_id = @pid
                LIMIT 1
            ),
            fraud AS (
                SELECT distinct_id FROM {T('fraudsters')} WHERE distinct_id = @pid
                UNION ALL
                SELECT distinct_id FROM {T('potential_fraudsters')} WHERE distinct_id = @pid
            )
            SELECT p.source, p.install_date, p.last_event_time,
                   (SELECT COUNT(*) FROM fraud) > 0 AS is_fraud
            FROM player p
        """, [bq_param("pid", "STRING", player_id)])

        for r in rows:
            if r.is_fraud or r.source not in OW_ATTRIBUTION_WINDOWS or not r.install_date or not r.last_event_time:
                break
            window_days = OW_ATTRIBUTION_WINDOWS[r.source]
            if r.source == "almedia" and r.install_date < _ALMEDIA_WINDOW_CHANGE_DATE:
                window_days = _ALMEDIA_PRE_CHANGE_WINDOW_DAYS
            days_left = (r.install_date + timedelta(days=window_days) - date.today()).days
            last_event_time = r.last_event_time
            if last_event_time.tzinfo is None:
                last_event_time = last_event_time.replace(tzinfo=timezone.utc)
            days_since_active = (datetime.now(timezone.utc) - last_event_time).days
            if days_left <= MERGECOINS_MAX_DAYS_LEFT_IN_WINDOW and days_since_active <= MERGECOINS_MIN_RECENT_ACTIVITY_DAYS:
                result = {"eligible": True, "source": r.source}
    except Exception as e:
        # WHY fail closed to None rather than raise: a lookup failure must fall through to the
        # existing Offer-1-style eligibility path, never block or 500 a signup outright.
        logger.warning(f"MergeCoins eligibility check failed for {player_id}: {e}")
        result = None

    cache_ref.set({"result": result, "cached_at": datetime.now(timezone.utc)})
    return result


def is_eligible_player(player_id: str) -> bool:
    """Check if player is in the eligible list (BQ assignment table).
    Only eligible players can get offers — prevents URL sharing abuse."""
    try:
        rows = bq_query(f"""
            SELECT 1 FROM {T(PLAYER_ASSIGNMENTS_TABLE)}
            WHERE distinct_id = @pid LIMIT 1
        """, [bq_param("pid", "STRING", player_id)])
        return any(True for _ in rows)
    except Exception as e:
        logger.warning(f"Eligibility check failed: {e}")
    return False


def match_segment(fs, player_id: str, current_chapter: int) -> dict:
    """Match player to a segment. Tries the real MergeCoins targeting first (offerwall source +
    attribution window + recent activity, chapter 50-129); falls back to the original Offer-1-style
    eligibility list + fixed chapter-bucket target for anyone who doesn't qualify under the new rule
    (wrong chapter range, non-offerwall source, inactive, or the two tiers still pending Itai)."""

    if player_id in MERGECOINS_TEST_PLAYER_IDS:
        return {
            "segment_id": "test_mergecoins", "reward_amount": 50.0,
            "target_chapter": current_chapter + MERGECOINS_TARGET_OFFSET,
            "checkpoint_chapter": current_chapter + MERGECOINS_CHECKPOINT_OFFSET,
            "time_limit_days": MERGECOINS_WINDOW_DAYS, "is_mergecoins": True,
        }

    if check_mergecoins_eligibility(player_id):
        reward_info = mergecoins_segment_reward(current_chapter)
        if reward_info:
            return {
                "segment_id": reward_info["segment_id"],
                "reward_amount": reward_info["reward_amount"],
                "target_chapter": current_chapter + MERGECOINS_TARGET_OFFSET,
                "checkpoint_chapter": current_chapter + MERGECOINS_CHECKPOINT_OFFSET,
                "time_limit_days": MERGECOINS_WINDOW_DAYS, "is_mergecoins": True,
            }

    # Fall back to the original Offer-1-style eligibility (assignment list + fixed bucket target)
    if not is_eligible_player(player_id):
        raise HTTPException(400, "No offer available for your account.")

    assignment = assign_segment(current_chapter)
    if not assignment:
        raise HTTPException(400, "No offer available for your current progress level.")

    return assignment


def build_mergecoins_payload(milestone: dict, current_chapter: Optional[int],
                              start_chapter: Optional[int]) -> Optional[dict]:
    """Dashboard progress payload for the two-threshold MergeCoins UI (checkpoint + target markers
    on one bar, no cash-out action — see the finalized mechanic, 2026-09-09). `milestone` is the raw
    Firestore milestone doc dict. Only milestones stamped is_mergecoins=True at signup (real
    eligibility path or the MERGECOINS_TEST_PLAYER_IDS override — both go through match_segment)
    carry a checkpoint_chapter; the original single-milestone offer has none, so it correctly gets
    `mergecoins: null` and its dashboard is unaffected.
    start_chapter (current_chapter_at_signup) is included so the frontend can place both markers
    proportionally along the bar instead of hardcoding the +11/+15 offsets client-side.
    """
    if not milestone or not milestone.get("is_mergecoins") or not milestone.get("checkpoint_chapter"):
        return None
    current_chapter = current_chapter or 0
    return {
        "current_chapter": current_chapter,
        "start_chapter": start_chapter or 0,
        "checkpoint_chapter": milestone["checkpoint_chapter"],
        "checkpoint_reward_amount": milestone.get("checkpoint_reward_amount"),
        "target_chapter": milestone["target_chapter"],
        "reward_amount": milestone["reward_amount"],
        "checkpoint_reached": current_chapter > milestone["checkpoint_chapter"],
    }


# ── LiveOps popup time lookup ──────────────────────────────────────

def get_popup_first_shown(player_id: str, liveops_id: str) -> Optional[datetime]:
    try:
        rows = bq_query(f"""
            SELECT first_shown_at
            FROM {T(LIVEOPS_POPUP_TABLE)}
            WHERE player_id = @pid AND liveops_id = @lid
            LIMIT 1
        """, [bq_param("pid", "STRING", player_id), bq_param("lid", "STRING", liveops_id)])
        for r in rows:
            if r.first_shown_at:
                ts = r.first_shown_at
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                return ts
    except Exception as e:
        logger.warning(f"LiveOps popup lookup failed: {e}")
    return None


# ── Combined player validation (single BQ query) ─────────────────

def validate_and_get_player(player_id: str) -> dict:
    """Single BQ query: check player exists, fraud status, and current chapter.
    Uses Firestore cache to avoid BQ on repeat lookups.
    Raises uniform error message for both not-found and fraud-flagged.
    """
    is_whitelisted = player_id in TEST_WHITELIST

    fs = get_fs()
    cache_doc = fs.collection("player_cache").document(player_id).get()
    if cache_doc.exists:
        cached = cache_doc.to_dict()
        cache_age = (datetime.now(timezone.utc) - cached["cached_at"]).total_seconds()
        if cache_age < 600:  # 10 min TTL (reduced from 1h to close fraud detection window)
            if not is_whitelisted and (cached.get("is_fraud") or not cached.get("exists")):
                raise HTTPException(400, "Unable to verify eligibility. Please contact support.")
            if is_whitelisted and not cached.get("exists"):
                raise HTTPException(400, "Unable to verify eligibility. Please contact support.")
            return cached

    rows = bq_query(f"""
        WITH player AS (
            SELECT distinct_id FROM {T('dim_player')}
            WHERE distinct_id = @pid LIMIT 1
        ),
        fraud AS (
            SELECT distinct_id, 'fraudsters' as source FROM {T('fraudsters')}
            WHERE distinct_id = @pid
            UNION ALL
            SELECT distinct_id, 'potential_fraudsters' as source FROM {T('potential_fraudsters')}
            WHERE distinct_id = @pid
        ),
        chapter AS (
            SELECT MAX(CAST(chapter AS INT64)) as max_chapter
            FROM {T('agg_player_chapter_daily')}
            WHERE distinct_id = @pid
        )
        SELECT
            (SELECT COUNT(*) FROM player) > 0 AS player_exists,
            (SELECT COUNT(*) FROM fraud) > 0 AS is_fraud,
            (SELECT source FROM fraud LIMIT 1) AS fraud_table,
            (SELECT max_chapter FROM chapter) AS max_chapter
    """, [bq_param("pid", "STRING", player_id)])

    result = {"exists": False, "is_fraud": False, "fraud_table": None, "max_chapter": 0}
    for r in rows:
        result = {
            "exists": r.player_exists,
            "is_fraud": r.is_fraud,
            "fraud_table": r.fraud_table,
            "max_chapter": r.max_chapter or 0,
        }

    fs.collection("player_cache").document(player_id).set({
        **result,
        "cached_at": datetime.now(timezone.utc),
    })

    # Uniform error message — don't reveal whether player exists or is fraud-flagged
    if not result["exists"] or (result["is_fraud"] and not is_whitelisted):
        raise HTTPException(400, "Unable to verify eligibility. Please contact support.")

    return result


def check_fraud_status(player_id: str) -> bool:
    """Re-check fraud tables for a player. Returns True if fraud-flagged."""
    rows = bq_query(f"""
        SELECT COUNT(*) as cnt FROM (
            SELECT distinct_id FROM {T('fraudsters')} WHERE distinct_id = @pid
            UNION ALL
            SELECT distinct_id FROM {T('potential_fraudsters')} WHERE distinct_id = @pid
        )
    """, [bq_param("pid", "STRING", player_id)])
    for r in rows:
        return r.cnt > 0
    return False


def get_player_max_chapter(player_id: str) -> int:
    """Player's highest chapter — uses the FRESHEST source and takes the higher of today's
    real-time events (vmp_master_event_normalized) vs the daily aggregate.
    WHY the higher (do NOT switch to agg-only): the daily rollup (agg_player_chapter_daily /
    dim_player.last_chapter) only finalizes yesterday — today's in-progress advance isn't in it yet.
    A fast/paying player can climb several chapters same-day; vmp reflects it in real time.
    Verified 2026-07-30: a player genuinely reached ch126 (paid her way, monotonic climb 124→126)
    while agg/dim still read 124 (today's row not yet rolled up). vmp was CORRECT, not an over-read —
    every prior day agg == vmp's same-day max. Using agg-only would lag completions ~a day and make
    the completion check disagree with reality. Date-partition filtered on both tables (org req)."""
    try:
        rows = bq_query(f"""
            SELECT MAX(CAST(chapter AS INT64)) as max_chapter
            FROM {T('vmp_master_event_normalized')}
            WHERE date >= CURRENT_DATE() AND distinct_id = @pid AND chapter IS NOT NULL
        """, [bq_param("pid", "STRING", player_id)])
        for r in rows:
            if r.max_chapter and r.max_chapter > 0:
                daily_rows = bq_query(f"""
                    SELECT MAX(CAST(chapter AS INT64)) as max_chapter
                    FROM {T('agg_player_chapter_daily')}
                    WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) AND distinct_id = @pid
                """, [bq_param("pid", "STRING", player_id)])
                daily_max = 0
                for dr in daily_rows:
                    daily_max = dr.max_chapter or 0
                return max(r.max_chapter, daily_max)
    except Exception as e:
        logger.warning(f"Real-time chapter lookup failed, falling back to daily: {e}")

    # Fallback: daily aggregate (date-partition filtered)
    rows = bq_query(f"""
        SELECT MAX(CAST(chapter AS INT64)) as max_chapter
        FROM {T('agg_player_chapter_daily')}
        WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) AND distinct_id = @pid
    """, [bq_param("pid", "STRING", player_id)])
    for r in rows:
        return r.max_chapter or 0
    return 0


# ── Event logging (stays in BQ) ────────────────────────────────────

def log_event(event_name, user_id=None, player_id=None, email=None, segment=None, properties=None):
    try:
        row = {
            "event_timestamp": datetime.now(timezone.utc).isoformat(),
            "event_name": event_name,
            "user_id": user_id,
            "player_id": player_id,
            "email": email,
            "segment": segment,
            "properties": json.dumps(properties or {}),
        }
        errors = get_bq().insert_rows_json(get_bq().dataset(BQ_DATASET).table("mergecash_events"), [row])
        if errors:
            logger.warning(f"Event log error: {errors}")
    except Exception as e:
        logger.warning(f"Event log failed: {e}")


# ── Slack notification ──────────────────────────────────────────────

def notify_reward_completed(email, player_id, segment, reward_amount):
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "🎉 MergeCash — Reward Ready"}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Email:*\n{email}"},
            {"type": "mrkdwn", "text": f"*Player ID:*\n{player_id}"},
            {"type": "mrkdwn", "text": f"*Segment:*\n{segment}"},
            {"type": "mrkdwn", "text": f"*Reward:*\n${reward_amount:.2f} Amazon Gift Card"},
            {"type": "mrkdwn", "text": f"*Time:*\n{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
        ]},
        {"type": "context", "elements": [
            {"type": "mrkdwn", "text": "Player completed their milestone — reward is *pending approval* in the admin panel."}
        ]},
    ]
    fallback = f"MergeCash reward ready: {email} — ${reward_amount:.2f} ({segment})"
    # Preferred: bot token → chat.postMessage (lets us control the display identity).
    if SLACK_BOT_TOKEN and SLACK_REWARDS_CHANNEL:
        try:
            resp = http_requests.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                json={"channel": SLACK_REWARDS_CHANNEL, "blocks": blocks, "text": fallback,
                      # username/icon apply only if the app has chat:write.customize; ignored otherwise
                      "username": "MergeCash", "icon_emoji": ":moneybag:"},
                timeout=10)
            body = resp.json()
            if not body.get("ok"):
                logger.error(f"Slack notify (bot) not ok: {body.get('error')}")
        except Exception as e:
            logger.error(f"Slack notify (bot) failed: {e}")
        return
    # Fallback: incoming webhook (if ever configured)
    if SLACK_REWARDS_WEBHOOK:
        try:
            http_requests.post(SLACK_REWARDS_WEBHOOK, json={"blocks": blocks}, timeout=10)
        except Exception as e:
            logger.error(f"Slack notify (webhook) failed: {e}")
        return
    logger.warning("notify_reward_completed: no Slack bot token or webhook configured — alert skipped")


# ── Help Scout ──────────────────────────────────────────────────────

def get_helpscout_token():
    if not HELPSCOUT_APP_ID or not HELPSCOUT_APP_SECRET:
        raise RuntimeError("Help Scout not configured")
    resp = http_requests.post("https://api.helpscout.net/v2/oauth2/token", json={
        "grant_type": "client_credentials",
        "client_id": HELPSCOUT_APP_ID,
        "client_secret": HELPSCOUT_APP_SECRET,
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()["access_token"]


def create_helpscout_conversation(email, subject, body):
    token = get_helpscout_token()
    resp = http_requests.post("https://api.helpscout.net/v2/conversations", json={
        "subject": f"MergeCash: {subject}",
        "customer": {"email": email},
        "mailboxId": HELPSCOUT_MAILBOX_ID,
        "type": "email",
        "status": "active",
        "threads": [{"type": "customer", "customer": {"email": email}, "text": body}],
    }, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, timeout=10)
    resp.raise_for_status()


# ── Email verification ─────────────────────────────────────────────

def generate_verification_code() -> str:
    """Generate a 6-digit numeric verification code."""
    return ''.join(random.choices(string.digits, k=6))


def send_verification_email(email, code):
    """Send 6-digit verification code to user via SendGrid."""
    if not SENDGRID_API_KEY:
        logger.info(f"Verification email NOT sent (SendGrid not configured): {email}")
        return False
    try:
        resp = http_requests.post("https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
            json={
                "personalizations": [{"to": [{"email": email}]}],
                "from": {"email": SENDER_EMAIL, "name": "MergeCash"},
                "subject": f"Your MergeCash verification code: {code}",
                "content": [{"type": "text/html", "value": f"""
                    <div style="font-family:-apple-system,sans-serif;max-width:520px;margin:0 auto;padding:32px;color:#222">
                        <h1 style="color:#0ea5e9;font-size:24px;margin-bottom:16px">Verify Your Email</h1>
                        <p style="font-size:16px;line-height:1.6">
                            Enter this code on the MergeCash website to see your personalized offer:
                        </p>
                        <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:12px;padding:24px;text-align:center;margin:24px 0">
                            <p style="color:#0ea5e9;font-size:42px;font-weight:800;margin:0;letter-spacing:8px;font-family:monospace">{code}</p>
                        </div>
                        <p style="font-size:14px;color:#888">
                            This code expires in 10 minutes. If you didn't sign up for MergeCash, ignore this email.
                        </p>
                    </div>"""}],
            }, timeout=10)
        # WHY: requests.post does NOT raise on 4xx — a SendGrid 401 "maximum credits exceeded"
        # (plan quota) returns a 4xx. Must check explicitly or emails silently vanish (2026-07-28 incident).
        if resp.status_code >= 300:
            logger.error(f"Verification email REJECTED for {email}: SendGrid {resp.status_code} {resp.text[:300]}")
            return False
        logger.info(f"Verification email sent to {email}")
        return True
    except Exception as e:
        logger.error(f"Verification email failed for {email}: {e}")
        return False


# ── Completion email (SendGrid) ───────────────────────────────────

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SENDER_EMAIL = os.getenv("MERGECASH_SENDER_EMAIL", "hq@peerplay.com")


def send_completion_email(email, reward_amount, target_chapter):
    if not SENDGRID_API_KEY:
        logger.info(f"Completion email NOT sent (SendGrid not configured): {email}")
        return
    try:
        resp = http_requests.post("https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
            json={
                "personalizations": [{"to": [{"email": email}]}],
                "from": {"email": SENDER_EMAIL, "name": "MergeCash"},
                "subject": "Milestone Completed! Your Amazon Gift Card is On the Way",
                "content": [{"type": "text/html", "value": f"""
                    <div style="font-family:-apple-system,sans-serif;max-width:520px;margin:0 auto;padding:32px;color:#222">
                        <h1 style="color:#0ea5e9;font-size:24px;margin-bottom:16px">Congratulations!</h1>
                        <p style="font-size:16px;line-height:1.6">
                            You've successfully completed <strong>Chapter {int(target_chapter)}</strong> in Merge Cruise.
                        </p>
                        <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:12px;padding:24px;text-align:center;margin:24px 0">
                            <p style="color:#666;font-size:13px;margin:0 0 4px">YOUR REWARD</p>
                            <p style="color:#0ea5e9;font-size:36px;font-weight:800;margin:0">${float(reward_amount):.2f}</p>
                            <p style="color:#666;font-size:14px;margin:4px 0 0">Amazon Gift Card</p>
                        </div>
                        <p style="font-size:15px;line-height:1.6;color:#444">
                            Your gift card is being processed and will be delivered to this email address
                            within <strong>24 hours</strong>.
                        </p>
                        <p style="font-size:14px;color:#888;margin-top:24px">
                            Thank you for playing!<br>
                            &mdash; The MergeCash Team
                        </p>
                    </div>"""}],
            }, timeout=10)
        if resp.status_code >= 300:
            logger.error(f"Completion email REJECTED for {email}: SendGrid {resp.status_code} {resp.text[:300]}")
            return
        logger.info(f"Completion email sent to {email}")
    except Exception as e:
        logger.error(f"SendGrid email failed for {email}: {e}")


# ── Reward creation with transaction (prevents double-rewards) ────

def complete_milestone_and_create_reward(fs, user_id, player_id, email, segment,
                                         milestone_doc_ref, target_chapter, reward_amount,
                                         payout_type="completion"):
    """Atomically complete milestone + create reward using Firestore transaction.
    Returns True if reward was created, False if already completed.
    Also sets notified=True flag to prevent duplicate notifications on retry.
    payout_type: 'completion' (full personal target reached) or 'checkpoint' (MergeCoins-only —
    window closed without full completion, but the checkpoint chapter was crossed). Stored on the
    reward for reporting only; does not change the transaction logic. Defaults to 'completion' so
    every existing (pre-MergeCoins) call site keeps behaving exactly as before."""
    now = datetime.now(timezone.utc)

    @firestore.transactional
    def txn(transaction):
        # Re-read milestone status inside transaction
        m_snapshot = milestone_doc_ref.get(transaction=transaction)
        if not m_snapshot.exists:
            return False
        m_data = m_snapshot.to_dict()
        if m_data.get("status") != "pending":
            return False  # Already completed by another path

        # Mark milestone completed with notified flag
        transaction.update(milestone_doc_ref, {
            "status": "completed",
            "completed_at": now,
            "notified": True,  # Prevents duplicate notifications on retry
        })

        # Create reward
        reward_ref = fs.collection("rewards").document(str(uuid.uuid4()))
        transaction.set(reward_ref, {
            "user_id": user_id, "player_id": player_id, "email": email,
            "segment": segment, "reward_type": "amazon_gift_card",
            "reward_amount": reward_amount, "status": "pending_approval",
            "payout_type": payout_type,
            "admin_notes": None, "created_at": now, "fulfilled_at": None,
        })

        # Update user status
        transaction.update(fs.collection("users").document(user_id), {"status": "completed"})
        return True

    transaction = fs.transaction()
    return txn(transaction)


# ── Request models ──────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: EmailStr
    player_id: str
    captcha_token: Optional[str] = None
    liveops_id: Optional[str] = None
    source_url_params: Optional[dict] = None

    def model_post_init(self, __context):
        if self.source_url_params:
            if len(json.dumps(self.source_url_params)) > 2048:
                raise ValueError("source_url_params too large")
            self.source_url_params = {k: str(v)[:256] for k, v in list(self.source_url_params.items())[:20]}


class LoginRequest(BaseModel):
    email: EmailStr


class ContactRequest(BaseModel):
    email: EmailStr
    player_id: Optional[str] = None
    subject: str
    message: str
    captcha_token: Optional[str] = None

    def model_post_init(self, __context):
        if len(self.subject) > 200:
            raise ValueError("Subject too long")
        if len(self.message) > 5000:
            raise ValueError("Message too long")


# ── Endpoints ───────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/signup")
def signup(req: SignupRequest, request: Request):
    fs = get_fs()
    client_ip = get_client_ip(request)
    player_id = validate_player_id(req.player_id)
    email = normalize_email(req.email)

    check_rate_limit(f"signup:{client_ip}", max_requests=5, window_seconds=60)

    # Check if email already exists
    existing = list(fs.collection("users").where("email", "==", email).limit(1).stream())
    if existing:
        doc = existing[0]
        token = create_token(doc.id)
        log_event("login", user_id=doc.id, email=email)
        return {"token": token, "user_id": doc.id, "is_new": False}

    # CAPTCHA
    recaptcha_secret = get_recaptcha_secret()
    if recaptcha_secret:
        if not req.captcha_token:
            raise HTTPException(400, "Please complete the CAPTCHA")
        resp = http_requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={"secret": recaptcha_secret, "response": req.captcha_token},
            timeout=5,
        )
        captcha_result = resp.json()
        if not captcha_result.get("success"):
            log_event("captcha_failed", properties={"ip": client_ip})
            raise HTTPException(400, "CAPTCHA verification failed")
        if not captcha_hostname_ok(captcha_result, "signup"):
            log_event("captcha_failed", properties={"ip": client_ip, "reason": "hostname"})
            raise HTTPException(400, "CAPTCHA verification failed")

    # IP rate limit (persistent)
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    ip_docs = fs.collection("users").where("signup_ip", "==", client_ip).stream()
    recent_count = sum(1 for doc in ip_docs if doc.to_dict().get("created_at") and doc.to_dict()["created_at"] >= cutoff)
    if recent_count >= MAX_SIGNUPS_PER_IP_PER_DAY:
        raise HTTPException(429, "Too many signups from this IP")

    # Check player_id uniqueness
    dupe = list(fs.collection("users").where("player_id", "==", player_id).limit(1).stream())
    if dupe:
        raise HTTPException(409, "This Player ID is already linked to another account")

    # Validate player + fraud check + get chapter (single BQ query with cache)
    player_data = validate_and_get_player(player_id)
    current_chapter = player_data["max_chapter"]

    # Match segment (Option B: per-player from BQ, Option A fallback: chapter ranges)
    segment = match_segment(fs, player_id, current_chapter)
    segment_id = segment["segment_id"]
    target_chapter = segment["target_chapter"]
    reward_amount = segment["reward_amount"]
    is_mergecoins = bool(segment.get("is_mergecoins"))
    checkpoint_chapter = segment.get("checkpoint_chapter")
    checkpoint_reward_amount = (
        round(reward_amount * MERGECOINS_CHECKPOINT_PCT, 2) if checkpoint_chapter else None
    )

    if current_chapter > target_chapter:
        raise HTTPException(400, "No offer available for your current progress level.")

    time_limit_days = segment.get("time_limit_days", DEFAULT_OFFER_WINDOW_DAYS)

    # Calculate offer expiry
    now = datetime.now(timezone.utc)
    liveops_id = validate_liveops_id(req.liveops_id or (req.source_url_params or {}).get("liveops_id", ""))

    popup_shown_at = None
    if liveops_id:
        popup_shown_at = get_popup_first_shown(player_id, liveops_id)

    if popup_shown_at:
        expires_at = popup_shown_at + timedelta(days=time_limit_days)
        if expires_at <= now:
            raise HTTPException(410, "This offer has expired")
    else:
        # No LiveOps data — check if this player has ANY popup record (with different liveops_id)
        # to prevent timer reset exploit (signing up without liveops_id to get fresh timer)
        # WHY the MERGECOINS_TEST_PLAYER_IDS carve-out: this anti-exploit anchor is correct for real
        # players (including real MergeCoins-eligible ones — no bypass for them), but a real,
        # long-lived test account genuinely has old unrelated promo-popup impressions that would
        # anchor it to a stale timer on every test run. Skipping it here just means the test account
        # falls through to the "genuine fallback" below. Delete alongside the rest of the test scaffold.
        if player_id not in MERGECOINS_TEST_PLAYER_IDS:
            try:
                any_popup = bq_query(f"""
                    SELECT MIN(first_shown_at) as earliest
                    FROM {T(LIVEOPS_POPUP_TABLE)}
                    WHERE player_id = @pid
                    LIMIT 1
                """, [bq_param("pid", "STRING", player_id)])
                for r in any_popup:
                    if r.earliest:
                        ts = r.earliest
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        popup_shown_at = ts
                        expires_at = popup_shown_at + timedelta(days=time_limit_days)
                        if expires_at <= now:
                            raise HTTPException(410, "This offer has expired")
                        break
            except HTTPException:
                raise
            except Exception:
                pass  # Table may not exist yet

        if not popup_shown_at:
            # Genuine fallback: no popup data at all, timer starts from signup
            expires_at = now + timedelta(days=time_limit_days)

    user_id = str(uuid.uuid4())

    fs.collection("users").document(user_id).set({
        "email": email,
        "player_id": player_id,
        "segment": segment_id,
        "liveops_id": liveops_id or None,
        "current_chapter_at_signup": current_chapter,
        "target_chapter": target_chapter,
        "reward_amount": reward_amount,
        "is_mergecoins": is_mergecoins,
        "checkpoint_chapter": checkpoint_chapter,
        "checkpoint_reward_amount": checkpoint_reward_amount,
        "signup_ip": client_ip,
        "status": "active",
        "email_verified": False,  # Email not verified — admin should check before fulfilling
        "created_at": now,
        "player_id_linked_at": now,
        "offer_expires_at": expires_at,
        "popup_first_shown_at": popup_shown_at,
        "source_url_params": json.dumps(req.source_url_params or {}),
    })

    milestone_id = f"ch{target_chapter}"
    fs.collection("users").document(user_id).collection("milestones").document(milestone_id).set({
        "player_id": player_id,
        "target_chapter": target_chapter,
        "reward_amount": reward_amount,
        "checkpoint_chapter": checkpoint_chapter,
        "checkpoint_reward_amount": checkpoint_reward_amount,
        "status": "pending",
        "completed_at": None,
        "created_at": now,
    })

    # Generate and send email verification code
    verification_code = generate_verification_code()
    fs.collection("users").document(user_id).update({
        "verification_code": verification_code,
        "verification_code_expires": now + timedelta(minutes=10),
        "verification_attempts": 0,
    })
    send_verification_email(email, verification_code)

    token = create_token(user_id)
    log_event("signup", user_id=user_id, player_id=player_id, email=email, segment=segment_id,
              properties={
                  "ip": client_ip, "current_chapter": current_chapter,
                  "target_chapter": target_chapter, "reward_amount": reward_amount,
                  "liveops_id": liveops_id,
              })

    return {
        "token": token, "user_id": user_id, "is_new": True,
        "requires_verification": True,
        "target_chapter": target_chapter,
        "reward_amount": reward_amount,
        "current_chapter": current_chapter,
        "expires_at": expires_at.isoformat(),
    }


@app.get("/api/verify-email")
def verify_email(request: Request, code: str = "", user=Depends(get_current_user)):
    """Verify email with 6-digit code via query param. GET used to avoid Cloud Armor OWASP body scanning."""
    check_rate_limit(f"verify:{user['sub']}", max_requests=5, window_seconds=60)

    if not code or len(code) != 6:
        raise HTTPException(400, "Please enter a valid 6-digit code")

    fs = get_fs()
    user_id = user["sub"]
    user_doc = fs.collection("users").document(user_id).get()
    if not user_doc.exists:
        raise HTTPException(404, "User not found")

    u = user_doc.to_dict()

    if u.get("email_verified"):
        return {"verified": True, "message": "Email already verified"}

    # Check attempt limit (max 5)
    attempts = u.get("verification_attempts", 0)
    if attempts >= 5:
        raise HTTPException(429, "Too many attempts. Please request a new code.")

    # Check code expiry
    code_expires = u.get("verification_code_expires")
    if code_expires and datetime.now(timezone.utc) > code_expires:
        raise HTTPException(410, "Code expired. Please request a new code.")

    # Check code
    stored_code = u.get("verification_code", "")
    fs.collection("users").document(user_id).update({
        "verification_attempts": attempts + 1,
    })

    if code.strip() != stored_code:
        log_event("email_verification_failed", user_id=user_id,
                  properties={"attempts": attempts + 1})
        raise HTTPException(400, "Invalid code. Please try again.")

    # Verified!
    fs.collection("users").document(user_id).update({
        "email_verified": True,
        "verification_code": None,  # Clear code
        "verification_code_expires": None,
    })
    log_event("email_verified", user_id=user_id, email=u["email"])

    return {"verified": True, "message": "Email verified!"}


@app.get("/api/resend-code")
def resend_verification_code(request: Request, user=Depends(get_current_user)):
    """Resend the verification code to the user's email."""
    check_rate_limit(f"resend:{user['sub']}", max_requests=3, window_seconds=300)

    fs = get_fs()
    user_id = user["sub"]
    user_doc = fs.collection("users").document(user_id).get()
    if not user_doc.exists:
        raise HTTPException(404, "User not found")

    u = user_doc.to_dict()
    if u.get("email_verified"):
        return {"message": "Email already verified"}

    # Generate new code
    now = datetime.now(timezone.utc)
    new_code = generate_verification_code()
    fs.collection("users").document(user_id).update({
        "verification_code": new_code,
        "verification_code_expires": now + timedelta(minutes=10),
        "verification_attempts": 0,
    })
    send_verification_email(u["email"], new_code)
    log_event("verification_code_resent", user_id=user_id, email=u["email"])

    return {"message": "New code sent!"}


@app.post("/api/login")
def login(req: LoginRequest, request: Request):
    client_ip = get_client_ip(request)
    check_rate_limit(f"login:{client_ip}", max_requests=5, window_seconds=60)

    fs = get_fs()
    email = normalize_email(req.email)
    docs = list(fs.collection("users").where("email", "==", email).limit(1).stream())
    if not docs:
        raise HTTPException(401, "Invalid email or account not found")
    doc = docs[0]
    u = doc.to_dict()
    token = create_token(doc.id)
    log_event("login", user_id=doc.id, email=email)
    return {
        "token": token, "user_id": doc.id,
        "requires_verification": not u.get("email_verified", False),
    }


@app.get("/api/dashboard")
def dashboard(request: Request, user=Depends(get_current_user)):
    check_rate_limit(f"dashboard:{user['sub']}", max_requests=10, window_seconds=60)

    fs = get_fs()
    user_id = user["sub"]

    user_doc = fs.collection("users").document(user_id).get()
    if not user_doc.exists:
        raise HTTPException(404, "User not found")
    u = user_doc.to_dict()

    # Block unverified users — only return verification status, not offer details
    if not u.get("email_verified", False):
        return {
            "user": {
                "email": u["email"],
                "email_verified": False,
                "status": u["status"],
            },
            "milestone": None,
            "reward": None,
        }

    if u["status"] == "active" and u.get("offer_expires_at") and datetime.now(timezone.utc) > u["offer_expires_at"]:
        fs.collection("users").document(user_id).update({"status": "expired"})
        u["status"] = "expired"

    user_data = {
        "email": u["email"], "player_id": u.get("player_id"),
        "status": u["status"],
        "email_verified": True,
        "target_chapter": u.get("target_chapter"),
        "reward_amount": u.get("reward_amount"),
        "current_chapter_at_signup": u.get("current_chapter_at_signup"),
        "current_chapter": u.get("current_chapter", u.get("current_chapter_at_signup")),
        "created_at": u["created_at"].isoformat() if u.get("created_at") else None,
        "offer_expires_at": u["offer_expires_at"].isoformat() if u.get("offer_expires_at") else None,
    }

    milestone = None
    milestone_raw = None
    if u.get("player_id"):
        for doc in fs.collection("users").document(user_id).collection("milestones").limit(1).stream():
            m = doc.to_dict()
            milestone_raw = m
            milestone = {
                "milestone_id": doc.id,
                "target_chapter": m["target_chapter"],
                "reward_amount": m["reward_amount"],
                "status": m["status"],
                "completed_at": m["completed_at"].isoformat() if m.get("completed_at") else None,
            }

    reward = None
    rewards = list(fs.collection("rewards").where("user_id", "==", user_id).limit(1).stream())
    if rewards:
        r = rewards[0].to_dict()
        reward = {
            "reward_id": rewards[0].id,
            "reward_amount": r["reward_amount"],
            "status": r["status"],
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            "fulfilled_at": r["fulfilled_at"].isoformat() if r.get("fulfilled_at") else None,
        }

    mergecoins = build_mergecoins_payload(
        milestone_raw, user_data["current_chapter"], user_data["current_chapter_at_signup"]
    ) if milestone_raw else None
    return {"user": user_data, "milestone": milestone, "reward": reward, "mergecoins": mergecoins}


@app.post("/api/check-progress")
def check_progress(request: Request, user=Depends(get_current_user)):
    check_rate_limit(f"progress:{user['sub']}", max_requests=3, window_seconds=60)

    fs = get_fs()
    user_id = user["sub"]

    user_doc = fs.collection("users").document(user_id).get()
    if not user_doc.exists:
        raise HTTPException(404, "User not found")
    u = user_doc.to_dict()
    player_id = u.get("player_id")
    segment = u.get("segment")
    email = u.get("email")
    status = u.get("status")
    offer_expires_at = u.get("offer_expires_at")

    if not u.get("email_verified", False):
        raise HTTPException(403, "Please verify your email first")
    if not player_id:
        raise HTTPException(400, "Link your Player ID first")
    if status == "fraud_flagged":
        raise HTTPException(403, "Account not eligible")
    if status == "expired":
        raise HTTPException(410, "Offer has expired")
    if status == "completed":
        return {"message": "Milestone already completed!", "completed": True, "max_chapter": 0}

    pending_doc = None
    pending_data = None
    for doc in fs.collection("users").document(user_id).collection("milestones").where("status", "==", "pending").limit(1).stream():
        pending_doc = doc
        pending_data = doc.to_dict()

    if not pending_data:
        return {"message": "Milestone already completed!", "completed": True, "max_chapter": 0}

    max_chapter = get_player_max_chapter(player_id)
    target_chapter = pending_data["target_chapter"]
    reward_amount = pending_data["reward_amount"]
    checkpoint_chapter = pending_data.get("checkpoint_chapter")
    checkpoint_reward_amount = pending_data.get("checkpoint_reward_amount")
    completed = False
    # WHY the expiry check moved here (2026-09-09), instead of failing fast before any of the above:
    # a MergeCoins checkpoint payout must still be evaluated even once the window has technically
    # expired (see the elif branch below) — mirrors the "completion checked before expiry" principle
    # verify_all_progress already uses for the full-target case. Side effect for the original
    # single-milestone offer (checkpoint_chapter is None there): a player who crosses the full target
    # in their exact final moments and calls this endpoint immediately now gets paid on the spot
    # instead of being told "expired" and waiting for the next scheduler run — strictly more
    # generous, never a regression.
    is_expired_now = bool(offer_expires_at and datetime.now(timezone.utc) > offer_expires_at)

    fs.collection("users").document(user_id).update({"current_chapter": max_chapter})

    if max_chapter > target_chapter:
        # Full personal target reached — pays 100%. Same path for MergeCoins and the original
        # single-milestone offer.
        if player_id not in TEST_WHITELIST and check_fraud_status(player_id):
            fs.collection("users").document(user_id).update({"status": "fraud_flagged"})
            log_event("fraud_flagged_at_completion", user_id=user_id, player_id=player_id,
                      properties={"source": "check_progress"})
            raise HTTPException(403, "Account not eligible")

        # Use transaction to prevent double-reward
        created = complete_milestone_and_create_reward(
            fs, user_id, player_id, email, segment,
            pending_doc.reference, target_chapter, reward_amount, payout_type="completion"
        )
        if created:
            log_event("milestone_completed_reward_created", user_id=user_id, player_id=player_id,
                      email=email, segment=segment,
                      properties={"reward_amount": reward_amount, "payout_type": "completion"})
            notify_reward_completed(email, player_id, segment, reward_amount)
            send_completion_email(email, reward_amount, target_chapter)
        completed = True

    elif is_expired_now:
        # Window closed without full completion. MergeCoins players (checkpoint_chapter is set) still
        # get the checkpoint reward if they crossed it — auto-paid, no player action, per the
        # finalized mechanic (2026-09-09). The original single-milestone offer has no
        # checkpoint_chapter, so it always falls straight through to plain expiry, unchanged.
        if checkpoint_chapter and max_chapter > checkpoint_chapter:
            if player_id not in TEST_WHITELIST and check_fraud_status(player_id):
                fs.collection("users").document(user_id).update({"status": "fraud_flagged"})
                log_event("fraud_flagged_at_completion", user_id=user_id, player_id=player_id,
                          properties={"source": "check_progress_checkpoint"})
                raise HTTPException(403, "Account not eligible")

            created = complete_milestone_and_create_reward(
                fs, user_id, player_id, email, segment,
                pending_doc.reference, target_chapter, checkpoint_reward_amount, payout_type="checkpoint"
            )
            if created:
                log_event("milestone_completed_reward_created", user_id=user_id, player_id=player_id,
                          email=email, segment=segment,
                          properties={"reward_amount": checkpoint_reward_amount, "payout_type": "checkpoint"})
                notify_reward_completed(email, player_id, segment, checkpoint_reward_amount)
                send_completion_email(email, checkpoint_reward_amount, target_chapter)
            completed = True
        else:
            fs.collection("users").document(user_id).update({"status": "expired"})
            raise HTTPException(410, "Offer has expired")

    return {"max_chapter": max_chapter, "target_chapter": target_chapter, "completed": completed}


@app.post("/api/contact")
def contact(req: ContactRequest, request: Request):
    client_ip = get_client_ip(request)
    check_rate_limit(f"contact:{client_ip}", max_requests=3, window_seconds=600)

    recaptcha_secret = get_recaptcha_secret()
    if recaptcha_secret:
        if not req.captcha_token:
            raise HTTPException(400, "Please complete the CAPTCHA")
        resp = http_requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={"secret": recaptcha_secret, "response": req.captcha_token},
            timeout=5,
        )
        captcha_result = resp.json()
        if not captcha_result.get("success"):
            log_event("captcha_failed", properties={"ip": client_ip, "source": "contact"})
            raise HTTPException(400, "CAPTCHA verification failed")
        if not captcha_hostname_ok(captcha_result, "contact"):
            log_event("captcha_failed", properties={"ip": client_ip, "source": "contact", "reason": "hostname"})
            raise HTTPException(400, "CAPTCHA verification failed")

    log_event("contact_form", email=req.email, player_id=req.player_id,
              properties={"subject": req.subject})

    body = f"Player ID: {req.player_id or 'N/A'}\n\n{req.message}"
    try:
        create_helpscout_conversation(req.email, req.subject, body)
    except Exception as e:
        logger.error(f"Help Scout ticket creation failed: {e}")
        raise HTTPException(500, "Failed to send message. Please try again or email hq@peerplay.com directly.")

    return {"message": "Message sent! We'll get back to you within 24 hours."}


# ── Admin endpoints (protected by INTERNAL_SECRET) ───────────────────

def require_internal(request: Request):
    """Auth for the Cloud Scheduler-driven /api/internal/* endpoints.

    Accepts EITHER a Google-signed OIDC id_token from SCHEDULER_SA (preferred — nothing secret
    lives in the scheduler job config) OR the legacy static INTERNAL_SECRET bearer.

    WHY both are accepted: it lets the OIDC cutover roll out without a flag-day. The app is
    deployed accepting both FIRST, then the jobs are migrated one at a time and force-run; a bad
    audience or SA can be reverted per-job without the completion/payout pass ever going dark.
    Drop the static leg once all three jobs are confirmed on OIDC.
    """
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(403, "Forbidden")

    if SCHEDULER_SA:
        try:
            claims = google_id_token.verify_oauth2_token(
                token, google_auth_requests.Request(), audience=OIDC_AUDIENCE or None
            )
            if claims.get("email") == SCHEDULER_SA and claims.get("email_verified"):
                return
        except Exception:
            # Not a valid OIDC token (or not ours) — fall through to the static-secret leg.
            pass

    if INTERNAL_SECRET and token == INTERNAL_SECRET:
        return

    log_event("internal_access_failed",
              properties={"ip": get_client_ip(request), "path": request.url.path})
    raise HTTPException(403, "Forbidden")


def _gateway_identity_shape(request: Request) -> dict:
    """OBSERVE-ONLY (SSO step 1): describe the gateway-injected identity so token-less SSO authz can
    be designed off real data instead of assumptions.

    Returns SHAPE facts only — claim NAMES, issuer, email DOMAIN, presence booleans. NEVER the token
    and NEVER a full email address. The signature is intentionally NOT verified here; that is step
    2's job. This only answers "is there a verifiable Google identity in front of us, and which claim
    carries it?".

    WHY the blanket except: this is telemetry bolted onto an auth path. A diagnostic must never be
    able to break a login — that is the 2026-08-04 lesson. It returns partial data or an error name,
    and can never raise into the caller.
    """
    out = {}
    try:
        out["iap_jwt_hdr"] = bool(request.headers.get("X-Goog-IAP-JWT-Assertion"))
        gu = request.headers.get("X-Goog-Authenticated-User-Email", "")
        out["goog_email_hdr"] = bool(gu)
        if gu:
            # SPOOF TEST instrumentation. DOMAIN ONLY — never the local part, so a real operator's
            # address is not written to the event log. `value_count` is the security-critical bit: if
            # the gateway APPENDS to a client-supplied header instead of replacing it, we see >1 value
            # and must not trust position. `scheme` is the "accounts.google.com:" prefix IAP uses.
            out["goog_email_value_count"] = len([p for p in gu.split(",") if p.strip()])
            out["goog_email_scheme"] = gu.split(":")[0] if ":" in gu else None
            out["goog_email_domain"] = gu.rsplit("@", 1)[-1] if "@" in gu else None
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            out["authz_bearer"] = False
            return out
        out["authz_bearer"] = True
        raw = auth[7:]
        out["authz_len"] = len(raw)
        claims = pyjwt.decode(raw, options={"verify_signature": False, "verify_aud": False})
        out["claims"] = sorted(claims.keys())
        out["iss"] = claims.get("iss")
        # aud VALUE (not just presence): the SSO check must verify against the audience the gateway
        # actually mints, and pinning it to the service URL (correct for the schedulers) produced
        # InvalidValue. A token audience is a URL/client-id, not a secret.
        out["aud"] = claims.get("aud")
        out["azp"] = claims.get("azp")
        # Full SA address when this is a service account (infrastructure identifier, not PII) so the
        # SSO check can pin to it. Human addresses stay domain-only below.
        _em = claims.get("email") or ""
        out["sa_email"] = _em if _em.endswith(".iam.gserviceaccount.com") else None
        out["has_email"] = bool(claims.get("email"))
        out["has_sub"] = bool(claims.get("sub"))
        out["email_verified"] = claims.get("email_verified")
        out["hd"] = claims.get("hd")  # Google Workspace domain claim, if present
        em = claims.get("email")
        if isinstance(em, str) and "@" in em:
            out["email_domain"] = em.rsplit("@", 1)[-1]
    except Exception as e:
        out["shape_error"] = type(e).__name__
    return out


FRESH_CACHE_TTL_S = int(os.getenv("MERGECASH_INSIGHTS_CACHE_TTL", "90"))
_INSIGHTS_CACHE = {"key": None, "at": 0.0, "data": None}
SSO_ALLOWED_DOMAIN = os.getenv("MERGECASH_SSO_DOMAIN", "peerplay.com")
# Break-glass re-enable of the retired shared admin token. OFF unless explicitly set — leaving it on
# would keep the query-param leak that SSO exists to remove. See require_admin().
ADMIN_TOKEN_FALLBACK = os.getenv("MERGECASH_ADMIN_TOKEN_FALLBACK", "").lower() not in ("", "0", "false", "no")
SSO_GATEWAY_SA = os.getenv("MERGECASH_SSO_GATEWAY_SA", "")
# ⚠️ SSO_AUDIENCE IS NOT OIDC_AUDIENCE — do not merge them.
# Measured 2026-08-04: the cloudrun-gateway mints its bearer with aud = the **mergecash-WEB** service
# URL (it authenticates to nginx, which then forwards the original Authorization header on to this
# API). OIDC_AUDIENCE is the **API** URL and belongs to the Cloud Scheduler tokens in
# require_internal(). Using OIDC_AUDIENCE here produced InvalidValue on every request — caught by
# shadow mode before SSO gated anything.
SSO_AUDIENCE = os.getenv("MERGECASH_SSO_AUDIENCE", "")
_GOOGLE_CERTS = {"certs": None, "at": 0.0}
_CERTS_TTL_S = 3600


def _google_certs():
    """Google's OAuth2 signing certs, cached for an hour.

    WHY cached: google.oauth2.id_token.verify_oauth2_token re-fetches certs on EVERY call, which
    would put a synchronous HTTPS round-trip in front of every admin request.
    """
    now = time.time()
    if _GOOGLE_CERTS["certs"] is None or now - _GOOGLE_CERTS["at"] > _CERTS_TTL_S:
        import requests as _rq
        r = _rq.get("https://www.googleapis.com/oauth2/v1/certs", timeout=5)
        r.raise_for_status()
        _GOOGLE_CERTS["certs"] = r.json()
        _GOOGLE_CERTS["at"] = now
    return _GOOGLE_CERTS["certs"]


def evaluate_sso(request: Request) -> dict:
    """Decide whether this request would be authorised by SSO alone. NEVER raises.

    Two factors, because neither is sufficient alone:
      1. The gateway-injected `Authorization` bearer is CRYPTOGRAPHICALLY verified against Google's
         public certs (+ audience). This proves the request genuinely transited the gateway rather
         than hitting the service directly — that bearer is the GATEWAY'S SERVICE ACCOUNT, never the
         human, so it authenticates the CHANNEL, not the person.
      2. Only then is `X-Goog-Authenticated-User-Email` trusted for WHO, requiring @SSO_ALLOWED_DOMAIN.
         Safe because the gateway was measured (2026-08-04 spoof test) to REPLACE a client-supplied
         value rather than append to it — a forged attacker@evil.example never reached the app and the
         value count stayed 1.
    Returns {'ok': bool, 'why': str, ...} and is log-only until the flip.
    """
    out = {"ok": False, "why": "unknown"}
    try:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            out["why"] = "no_bearer"
            return out
        from google.auth import jwt as google_jwt
        claims = google_jwt.decode(auth[7:], certs=_google_certs(), verify=True,
                                   audience=SSO_AUDIENCE or None)
        out["jwt_verified"] = True
        sa = claims.get("email") or ""
        # A service-account address is an infrastructure identifier, not PII — log it in full so the
        # flip can pin to it. Human addresses stay domain-only, below.
        out["gateway_sa"] = sa if sa.endswith(".iam.gserviceaccount.com") else None
        if SSO_GATEWAY_SA and sa != SSO_GATEWAY_SA:
            out["why"] = "gateway_sa_mismatch"
            return out
        gu = request.headers.get("X-Goog-Authenticated-User-Email", "")
        if not gu:
            out["why"] = "no_user_header"
            return out
        if len([p for p in gu.split(",") if p.strip()]) != 1:
            out["why"] = "multi_value_user_header"  # appending proxy → position is untrustworthy
            return out
        dom = gu.rsplit("@", 1)[-1].strip().lower() if "@" in gu else ""
        out["user_domain"] = dom or None
        if dom != SSO_ALLOWED_DOMAIN:
            out["why"] = "domain_not_allowed"
            return out
        out["ok"] = True
        out["why"] = "verified_gateway_jwt_and_user_domain"
        return out
    except Exception as e:
        out["why"] = f"error:{type(e).__name__}"
        return out


def require_admin(request: Request):
    """Authorise the admin panel by SSO identity. NO SHARED TOKEN.

    The operator has already proven who they are to the cloudrun-gateway (VPN + Google login) before
    the page even loads, so a shared password added no security — it only added a credential to leak,
    rotate and paste. It leaked: because `admin.html` sent it as a `?_admin_token=` QUERY PARAM and
    Cloud Run logs request URLs in full, the live admin token sat in 568 request-log entries between
    2026-07-06 and 2026-08-04, readable by anyone with logging.viewer, replenished on every page load.
    Authorising off the gateway identity deletes that whole class of problem.

    evaluate_sso() does the work: cryptographically verify the gateway's bearer (proving the request
    transited the gateway), then trust X-Goog-Authenticated-User-Email for WHO and require the
    allowed domain. Cutover was proven in shadow mode first — 34/34 real admin requests evaluated
    ok=true, 0 failures, before this became the gate.
    """
    sso = evaluate_sso(request)
    if sso.get("ok"):
        log_event("admin_access", properties={"ip": get_client_ip(request),
                                              "auth": "sso", "sso": sso})
        return

    # BREAK-GLASS ONLY, off by default (MERGECASH_ADMIN_TOKEN_FALLBACK unset in deploy.sh).
    # WHY it exists: if SSO ever fails wholesale (gateway reconfigured, audience changed), this
    # re-enables the old token via env + redeploy without a code rollback. WHY it is OFF: leaving it on
    # would keep the query-param leak alive, which is the entire thing this change removes.
    if ADMIN_TOKEN_FALLBACK:
        secret = (request.headers.get("X-Admin-Token", "")
                  or request.query_params.get("_admin_token", "")).strip()
        if INTERNAL_SECRET and secret == INTERNAL_SECRET.strip():
            logger.warning("admin authorised via BREAK-GLASS token fallback — SSO said: "
                           f"{sso.get('why')}. Disable MERGECASH_ADMIN_TOKEN_FALLBACK once fixed.")
            log_event("admin_access", properties={"ip": get_client_ip(request),
                                                  "auth": "token_break_glass", "sso": sso})
            return

    # sso.why is the whole diagnostic now (no_bearer / domain_not_allowed / gateway_sa_mismatch /
    # multi_value_user_header / error:*), so the old token fingerprint fields are gone — a hash of a
    # live credential should not accumulate in an events table once nothing depends on it.
    log_event("admin_access_failed", properties={"ip": get_client_ip(request),
                                                 "token_fallback_enabled": ADMIN_TOKEN_FALLBACK,
                                                 "sso": sso})
    raise HTTPException(403, "Forbidden")


class FulfillRewardRequest(BaseModel):
    gift_card_code: Optional[str] = None
    admin_notes: Optional[str] = None
    send_email: Optional[bool] = True  # Send gift card code to user via email
    sent_directly: Optional[bool] = False  # card already delivered to the player (Amazon email to recipient) → send a heads-up notification, show NO code


class UpdateRewardNotesRequest(BaseModel):
    """Note-only amendment to an already-fulfilled/denied reward. Deliberately has NO send_email or
    status field — see update_reward_notes() for why this is separate from FulfillRewardRequest."""
    admin_notes: str
    gift_card_code: Optional[str] = None  # None = leave the stored value untouched


def send_gift_card_email(email, gift_card_code, reward_amount):
    """Email the reward to the user via SendGrid. Accepts EITHER a claim CODE or a claim LINK.
    WHY both: Amazon 'apply-to-account' / animated eGifts have NO code — only a Redeem URL. If the
    value is a URL we render a 'Claim' button; otherwise we show the code. Lets the branded MergeCash
    email deliver link-based cards too (2026-07-30)."""
    if not SENDGRID_API_KEY:
        logger.info(f"Gift card email NOT sent (SendGrid not configured): {email}")
        return False
    amt = f"${float(reward_amount):.2f}"
    val = (gift_card_code or "").strip()
    if not val:
        # Notification-only: the card was delivered to the player directly (e.g. Amazon "email to recipient")
        claim_block = f"""
                        <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:12px;padding:24px;text-align:center;margin:24px 0">
                            <p style="color:#0ea5e9;font-size:32px;font-weight:800;margin:0">{amt}</p>
                            <p style="color:#666;font-size:14px;margin:6px 0 0">Amazon Gift Card</p>
                        </div>
                        <p style="font-size:15px;line-height:1.6;color:#444">
                            Your gift card has been sent to this email address by <strong>Amazon</strong>. Look for an email from
                            Amazon (do-not-reply@gift-cards.amazon.com) and click <strong>Redeem</strong> to add it to your account.
                            If you don't see it, please check your spam/promotions folder.
                        </p>"""
    elif val.lower().startswith("http"):
        claim_block = f"""
                        <div style="text-align:center;margin:24px 0">
                            <a href="{val}" style="display:inline-block;background:#0ea5e9;color:#fff;padding:16px 34px;border-radius:12px;font-weight:800;font-size:18px;text-decoration:none">Claim your {amt} Amazon Gift Card &rarr;</a>
                        </div>
                        <p style="font-size:15px;line-height:1.6;color:#444">
                            Click the button above to add your <strong>{amt} Amazon Gift Card</strong> to your Amazon account. Be signed in to Amazon when you click.
                        </p>"""
    else:
        claim_block = f"""
                        <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:12px;padding:24px;text-align:center;margin:24px 0">
                            <p style="color:#666;font-size:13px;margin:0 0 8px">YOUR GIFT CARD CODE</p>
                            <p style="color:#0ea5e9;font-size:28px;font-weight:800;margin:0;letter-spacing:2px;font-family:monospace">{val}</p>
                            <p style="color:#666;font-size:14px;margin:8px 0 0">{amt} Amazon Gift Card</p>
                        </div>
                        <p style="font-size:15px;line-height:1.6;color:#444">
                            To redeem, go to <strong>amazon.com</strong> and enter the code above at checkout,
                            or apply it to your account under "Gift Cards".
                        </p>"""
    try:
        resp = http_requests.post("https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
            json={
                "personalizations": [{"to": [{"email": email}]}],
                "from": {"email": SENDER_EMAIL, "name": "MergeCash"},
                "subject": "Your Amazon Gift Card is Here!",
                "tracking_settings": {"open_tracking": {"enable": True}, "click_tracking": {"enable": True, "enable_text": False}},
                "content": [{"type": "text/html", "value": f"""
                    <div style="font-family:-apple-system,sans-serif;max-width:520px;margin:0 auto;padding:32px;color:#222">
                        <h1 style="color:#0ea5e9;font-size:24px;margin-bottom:16px">Your Reward is Here!</h1>
                        <p style="font-size:16px;line-height:1.6">
                            Congratulations! Here is your <strong>{amt} Amazon Gift Card</strong> for completing your milestone in Merge Cruise.
                        </p>
                        {claim_block}
                        <p style="font-size:14px;color:#888;margin-top:24px">
                            Thank you for playing!<br>
                            &mdash; The MergeCash Team
                        </p>
                    </div>"""}],
            }, timeout=10)
        if resp.status_code >= 300:
            logger.error(f"Gift card email REJECTED for {email}: SendGrid {resp.status_code} {resp.text[:300]}")
            return False
        logger.info(f"Gift card email sent to {email}")
        return True
    except Exception as e:
        logger.error(f"Gift card email failed for {email}: {e}")
        return False


@app.get("/api/admin/rewards")
def list_rewards(request: Request, status: str = "pending_approval"):
    require_admin(request)
    check_rate_limit(f"admin:{get_client_ip(request)}", max_requests=30, window_seconds=60)
    fs = get_fs()
    rewards = []
    for doc in fs.collection("rewards").where("status", "==", status).stream():
        r = doc.to_dict()
        # Look up email_verified from user doc
        email_verified = True  # Default for older users
        user_docs = list(fs.collection("users").where("player_id", "==", r["player_id"]).limit(1).stream())
        if user_docs:
            email_verified = user_docs[0].to_dict().get("email_verified", True)
        rewards.append({
            "reward_id": doc.id,
            "user_id": r["user_id"],
            "player_id": r["player_id"],
            "email": r["email"],
            "email_verified": email_verified,
            "segment": r.get("segment"),
            "reward_amount": r["reward_amount"],
            "status": r["status"],
            "admin_notes": r.get("admin_notes"),
            "gift_card_code": r.get("gift_card_code"),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            "fulfilled_at": r["fulfilled_at"].isoformat() if r.get("fulfilled_at") else None,
        })
    return {"rewards": rewards, "count": len(rewards)}


@app.post("/api/admin/rewards/{reward_id}/fulfill")
def fulfill_reward(reward_id: str, req: FulfillRewardRequest, request: Request):
    require_admin(request)
    fs = get_fs()
    doc = fs.collection("rewards").document(reward_id).get()
    if not doc.exists:
        raise HTTPException(404, "Reward not found")
    r = doc.to_dict()
    if r["status"] == "fulfilled":
        raise HTTPException(400, "Reward already fulfilled")

    now = datetime.now(timezone.utc)
    fs.collection("rewards").document(reward_id).update({
        "status": "fulfilled",
        "fulfilled_at": now,
        "gift_card_code": req.gift_card_code,
        "admin_notes": req.admin_notes,
    })
    log_event("reward_fulfilled", user_id=r["user_id"], player_id=r["player_id"],
              email=r["email"], segment=r.get("segment"),
              properties={"reward_id": reward_id, "reward_amount": r["reward_amount"]})

    # Email the user. sent_directly → notification-only (Amazon already delivered the card; show no code).
    email_sent = False
    if req.send_email:
        display_val = None if req.sent_directly else req.gift_card_code
        email_sent = send_gift_card_email(r["email"], display_val, r["reward_amount"])

    return {"message": "Reward fulfilled", "reward_id": reward_id, "email_sent": email_sent}


@app.post("/api/admin/rewards/{reward_id}/deny")
def deny_reward(reward_id: str, req: FulfillRewardRequest, request: Request):
    require_admin(request)
    fs = get_fs()
    doc = fs.collection("rewards").document(reward_id).get()
    if not doc.exists:
        raise HTTPException(404, "Reward not found")

    fs.collection("rewards").document(reward_id).update({
        "status": "denied",
        "admin_notes": req.admin_notes,
    })
    log_event("reward_denied", user_id=doc.to_dict()["user_id"],
              properties={"reward_id": reward_id, "reason": req.admin_notes})

    return {"message": "Reward denied", "reward_id": reward_id}


@app.post("/api/admin/rewards/{reward_id}/notes")
def update_reward_notes(reward_id: str, req: UpdateRewardNotesRequest, request: Request):
    """Amend the fulfillment record (admin_notes + optional gift_card_code / order ref) on a reward
    that is ALREADY fulfilled or denied.

    WHY this exists separately from /fulfill: /fulfill hard-rejects an already-fulfilled reward
    (one-shot, so a double-click can't re-send a card or re-fire the reward_fulfilled event), which
    left NO way to record how a card was actually delivered once it had been marked fulfilled — the
    "Sent directly" button writes only a generic 'Sent directly to recipient'. Operators need to add
    the Amazon order number / delivery method afterwards for the audit trail (the 2026-07-30 $40
    fulfillment note is the template). This endpoint therefore touches ONLY the note fields and
    NEVER status / fulfilled_at, and never sends email — so it cannot be used to re-deliver a card.
    """
    require_admin(request)
    fs = get_fs()
    doc = fs.collection("rewards").document(reward_id).get()
    if not doc.exists:
        raise HTTPException(404, "Reward not found")
    r = doc.to_dict()

    updates = {"admin_notes": req.admin_notes}
    # WHY conditional: gift_card_code doubles as the order-ref field in the panel's Fulfilled column,
    # but an omitted value must not wipe a real code that is already stored.
    if req.gift_card_code is not None:
        updates["gift_card_code"] = req.gift_card_code
    fs.collection("rewards").document(reward_id).update(updates)

    # WHY a distinct event name: this is an audit amendment, NOT a funnel stage. Re-logging
    # reward_fulfilled here would double-count fulfillments in the mergecash-funnel dashboard.
    log_event("reward_note_updated", user_id=r.get("user_id"), player_id=r.get("player_id"),
              email=r.get("email"), segment=r.get("segment"),
              properties={"reward_id": reward_id, "status": r.get("status"),
                          "admin_notes": req.admin_notes})

    return {"message": "Reward notes updated", "reward_id": reward_id, "status": r.get("status")}


@app.get("/api/admin/users")
def list_users(request: Request, status: str = "active"):
    """List all users with full details. Admin only."""
    require_admin(request)
    check_rate_limit(f"admin:{get_client_ip(request)}", max_requests=30, window_seconds=60)
    fs = get_fs()
    users = []
    player_ids = []
    # Read every user ONCE, then fetch their milestone statuses CONCURRENTLY.
    # WHY: this used to query the `milestones` subcollection inside the loop — one sequential Firestore
    # round-trip per user. Fine at the 30-user go-live (~1s), but at 478 active users it meant 478
    # serial round-trips ≈ 13-18s per page load (measured: 15.5s, and 18.7s at peak). The Firestore
    # client is thread-safe, so a bounded pool collapses that to roughly one round-trip of wall-clock.
    # A single failed lookup must not fail the page, so each one degrades to "unknown" as before.
    # TEMPORARY phase timing. WHY: /api/admin/users sat at 15.5s, and TWO successive "obvious"
    # diagnoses (the milestones N+1, then the round-trip pattern) each failed to move it — pooling and
    # a collection-group scan both landed at ~5.8s. Guessing has cost two deploys; this attributes the
    # time instead. Remove once the real hotspot is fixed.
    _t = {}
    _t0 = time.time()
    user_docs = [(d.id, d.to_dict()) for d in
                 fs.collection("users").where("status", "==", status).stream()]
    _t["users_stream"] = round(time.time() - _t0, 2)
    _t["user_count"] = len(user_docs)
    _t0 = time.time()

    # ONE collection-group query for every milestone, instead of one query per user.
    # WHY: a pool of 16 still meant ~30 sequential batches of round-trips (~2.3s of the measured
    # 3.5-5.8s). A collection-group scan needs no composite index (verified) and returns all ~655
    # milestone docs in a single stream, so cost stops scaling with user count.
    # Same tie-break as the old `.limit(1)`: if a user somehow has >1 milestone, first-seen wins
    # (arbitrary before, arbitrary now — not a behaviour change).
    milestone_by_user = {}
    try:
        for m in fs.collection_group("milestones").stream():
            parent_user = m.reference.parent.parent
            if parent_user is not None and parent_user.id not in milestone_by_user:
                milestone_by_user[parent_user.id] = m.to_dict().get("status", "unknown")
    except Exception as e:
        # Degrade to "unknown" for everyone rather than failing the page — same as the old per-user
        # except path.
        logger.warning(f"milestone collection-group lookup failed: {type(e).__name__}: {e}")
    _t["milestones"] = round(time.time() - _t0, 2)
    _t["milestone_count"] = len(milestone_by_user)
    _t0 = time.time()

    for doc_id, u in user_docs:
        milestone_status = milestone_by_user.get(doc_id, "unknown")
        target_chapter = u.get("target_chapter")
        if u.get("player_id"):
            player_ids.append(u["player_id"])
        users.append({
            "user_id": doc_id,
            "player_id": u.get("player_id"),
            "email": u.get("email"),
            "email_verified": u.get("email_verified", True),
            "segment": u.get("segment"),
            "current_chapter_at_signup": u.get("current_chapter_at_signup"),
            "current_chapter": u.get("current_chapter", u.get("current_chapter_at_signup")),
            "target_chapter": target_chapter,
            "reward_amount": u.get("reward_amount"),
            "milestone_status": milestone_status,
            "status": u.get("status"),
            "created_at": u["created_at"].isoformat() if u.get("created_at") else None,
            "offer_expires_at": u["offer_expires_at"].isoformat() if u.get("offer_expires_at") else None,
        })

    _t["assemble"] = round(time.time() - _t0, 2)
    _t0 = time.time()

    # Batch fetch player insights from BQ for all player IDs.
    # CACHED (short TTL) because measurement showed this dominates the endpoint: phase timing gave
    # users_stream 0.29s / milestones 0.54s / assemble 0.00s / **bq_total 3.11s** of a ~4s request.
    # Only ~1.2s of that is query execution — the rest is BQ client round-trip overhead (job insert,
    # status polling, result fetch) x2 queries. An admin user LIST does not need sub-minute freshness;
    # the completion logic reads chapters independently and is untouched by this cache.
    # Keyed on the exact player-id set so a changed cohort can't serve stale rows.
    _cache_key = (status, hash(tuple(sorted(player_ids))))
    _cache_fresh = (_INSIGHTS_CACHE["key"] == _cache_key
                    and _INSIGHTS_CACHE["data"] is not None
                    and time.time() - _INSIGHTS_CACHE["at"] < FRESH_CACHE_TTL_S)
    _t["bq_cache"] = "hit" if _cache_fresh else "miss"
    if _cache_fresh:
        # COPY, never the cached object itself: the miss path mutates player_insights (setdefault for
        # the fresh-chapter leg), so handing out the cached dict by reference would let a later change
        # silently corrupt every subsequent hit.
        player_insights = dict(_INSIGHTS_CACHE["data"])
        player_ids = []  # short-circuits the single BQ block below (both queries live inside it)
    else:
        player_insights = {}
    if player_ids:
        try:
            rows = bq_query(f"""
                SELECT distinct_id, first_mediasource, install_date,
                       ltv_revenue, last_credit_balance, last_metapoint_balance, last_chapter
                FROM {T('dim_player')}
                WHERE distinct_id IN UNNEST(@pids)
            """, [bigquery.ArrayQueryParameter("pids", "STRING", player_ids)])
            for r in rows:
                player_insights[r.distinct_id] = {
                    "media_source": r.first_mediasource or "unknown",
                    "install_date": r.install_date.isoformat() if r.install_date else None,
                    "ltv": round(float(r.ltv_revenue), 2) if r.ltv_revenue else 0,
                    "credit_balance": int(r.last_credit_balance) if r.last_credit_balance else 0,
                    "metapoint_balance": int(r.last_metapoint_balance) if r.last_metapoint_balance else 0,
                    "live_chapter": int(r.last_chapter) if r.last_chapter else 0,
                }
        except Exception as e:
            logger.warning(f"Player insights lookup failed: {e}")

        # Fresh chapter: today's real-time vmp events LEAD the daily rollup — take the higher,
        # matching the completion logic. dim_player.last_chapter lags ~a day (2026-07-30: showed 124
        # for a player genuinely on 126). This keeps the admin "Current Ch" in sync with reality.
        try:
            vrows = bq_query(f"""
                SELECT distinct_id, MAX(CAST(chapter AS INT64)) AS max_ch
                FROM {T('vmp_master_event_normalized')}
                WHERE date >= CURRENT_DATE() AND distinct_id IN UNNEST(@pids) AND chapter IS NOT NULL
                GROUP BY distinct_id
            """, [bigquery.ArrayQueryParameter("pids", "STRING", player_ids)])
            for r in vrows:
                if r.max_ch:
                    ins = player_insights.setdefault(r.distinct_id, {})
                    ins["live_chapter"] = max(ins.get("live_chapter", 0), int(r.max_ch))
        except Exception as e:
            logger.warning(f"Fresh-chapter (vmp) lookup failed: {e}")

    for u in users:
        insights = player_insights.get(u.get("player_id"), {})
        u["media_source"] = insights.get("media_source", "unknown")
        u["install_date"] = insights.get("install_date")
        u["ltv"] = insights.get("ltv", 0)
        u["credit_balance"] = insights.get("credit_balance", 0)
        u["metapoint_balance"] = insights.get("metapoint_balance", 0)
        # Override Firestore chapter with live BQ data
        live_ch = insights.get("live_chapter", 0)
        if live_ch > 0:
            u["current_chapter"] = live_ch

    if _t.get("bq_cache") == "miss":
        _INSIGHTS_CACHE.update({"key": _cache_key, "at": time.time(), "data": player_insights})
    _t["bq_total"] = round(time.time() - _t0, 2)
    logger.info(f"list_users timing: {_t}")
    return {"users": users, "count": len(users)}


@app.get("/api/admin/view-as-user")
def admin_view_as_user(request: Request, player_id: str = ""):
    """Admin-only, READ-ONLY: return the exact dashboard payload a given player sees,
    looked up by player_id — no login or email code required. Lets ops verify what a
    signed-up user actually sees (offer, timer, progress, reward status).
    WHY read-only: unlike /api/dashboard (which lazily flips status to 'expired' and writes),
    this computes the displayed status without mutating Firestore, so viewing can't change state."""
    require_admin(request)
    check_rate_limit(f"admin:{get_client_ip(request)}", max_requests=30, window_seconds=60)
    player_id = (player_id or "").strip()
    if not player_id:
        raise HTTPException(400, "player_id required")

    fs = get_fs()
    user_docs = list(fs.collection("users").where("player_id", "==", player_id).limit(1).stream())
    if not user_docs:
        raise HTTPException(404, "No signed-up MergeCash user for that player_id")
    doc = user_docs[0]
    user_id = doc.id
    u = doc.to_dict()

    if not u.get("email_verified", False):
        # Player is stuck on the verification screen (mirrors /api/dashboard)
        payload = {
            "user": {"email": u["email"], "email_verified": False, "status": u["status"]},
            "milestone": None, "reward": None, "sees": "verification_screen",
        }
    else:
        # WHY: compute expiry for display WITHOUT writing — keeps this endpoint read-only
        display_status = u["status"]
        if display_status == "active" and u.get("offer_expires_at") and datetime.now(timezone.utc) > u["offer_expires_at"]:
            display_status = "expired"
        user_data = {
            "email": u["email"], "player_id": u.get("player_id"),
            "status": display_status, "email_verified": True,
            "target_chapter": u.get("target_chapter"),
            "reward_amount": u.get("reward_amount"),
            "current_chapter_at_signup": u.get("current_chapter_at_signup"),
            "current_chapter": u.get("current_chapter", u.get("current_chapter_at_signup")),
            "created_at": u["created_at"].isoformat() if u.get("created_at") else None,
            "offer_expires_at": u["offer_expires_at"].isoformat() if u.get("offer_expires_at") else None,
        }
        milestone = None
        for mdoc in fs.collection("users").document(user_id).collection("milestones").limit(1).stream():
            m = mdoc.to_dict()
            milestone = {
                "milestone_id": mdoc.id, "target_chapter": m["target_chapter"],
                "reward_amount": m["reward_amount"], "status": m["status"],
                "completed_at": m["completed_at"].isoformat() if m.get("completed_at") else None,
            }
        reward = None
        rewards = list(fs.collection("rewards").where("user_id", "==", user_id).limit(1).stream())
        if rewards:
            r = rewards[0].to_dict()
            reward = {
                "reward_id": rewards[0].id, "reward_amount": r["reward_amount"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                "fulfilled_at": r["fulfilled_at"].isoformat() if r.get("fulfilled_at") else None,
            }
        payload = {"user": user_data, "milestone": milestone, "reward": reward, "sees": "dashboard"}

    # Read-only diagnostics (NOT part of what the player sees): true live chapter (FRESH source —
    # same as the completion logic, which leads the daily rollup) vs the Firestore snapshot the
    # progress bar renders from. WHY get_player_max_chapter (not dim_player.last_chapter): the daily
    # rollup lags ~a day and showed 124 for a player genuinely on 126 (2026-07-30).
    try:
        live_chapter = get_player_max_chapter(player_id) or None
    except Exception as e:
        logger.warning(f"view-as-user live chapter lookup failed: {e}")
        live_chapter = None

    payload["_diagnostics"] = {
        "user_id": user_id,
        "server_now": datetime.now(timezone.utc).isoformat(),
        "live_chapter_bq": live_chapter,
        "firestore_current_chapter": u.get("current_chapter", u.get("current_chapter_at_signup")),
        "note": "Progress bar the player sees uses firestore_current_chapter (updates only when they tap 'Update My Progress'). live_chapter_bq is their true chapter now.",
    }
    return payload


@app.get("/api/admin/stats")
def admin_stats(request: Request):
    require_admin(request)
    fs = get_fs()
    stats = {"active": 0, "completed": 0, "expired": 0, "fraud_flagged": 0,
             "rewards_pending": 0, "rewards_fulfilled": 0, "rewards_denied": 0}
    for doc in fs.collection("users").stream():
        s = doc.to_dict().get("status", "")
        if s in stats:
            stats[s] += 1
    for doc in fs.collection("rewards").stream():
        s = doc.to_dict().get("status", "")
        key = f"rewards_{s}" if s != "pending_approval" else "rewards_pending"
        if key in stats:
            stats[key] += 1
    return stats


# ── Internal endpoint (Cloud Scheduler) ─────────────────────────────

def _crossed_chapter_before_deadline(player_id: str, threshold_chapter: int, deadline: datetime) -> bool:
    """True if `player_id` crossed `threshold_chapter` at or before `deadline`, per vmp event_time.
    Factored out of verify_all_progress's original target_chapter-only inline check (2026-09-09) so
    the same window-of-truth logic also covers checkpoint_chapter crossings, instead of duplicating
    the BQ query for a second threshold. On query failure, errs toward the player (pays) rather than
    block a legitimate reward on our own infra hiccup — same trade-off the original inline block made.
    """
    try:
        for cr in bq_query(f"""
            SELECT MIN(event_time) AS crossed_at
            FROM {T('vmp_master_event_normalized')}
            WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 DAY)
              AND distinct_id = @pid AND chapter IS NOT NULL
              AND CAST(chapter AS INT64) > @tgt
        """, [bq_param("pid", "STRING", player_id),
              bq_param("tgt", "INT64", threshold_chapter)]):
            ca = cr.crossed_at
            if ca:
                if ca.tzinfo is None:
                    ca = ca.replace(tzinfo=timezone.utc)
                return ca <= deadline
    except Exception as e:
        logger.error(f"crossing-time check failed for {player_id} (threshold {threshold_chapter}), paying anyway: {e}")
        return True
    return False


@app.post("/api/internal/verify-all-progress")
def verify_all_progress(request: Request):
    """Periodic job: check milestone for all active users with fraud re-check."""
    require_internal(request)

    fs = get_fs()
    now = datetime.now(timezone.utc)

    # Dead-man cross-check (mutual watchdog, no extra IAM): the hourly health monitor should have
    # logged within ~90m. If it's gone silent, THIS 4h job is the fallback that alerts (MergeCash
    # bot DM). The reverse — this scheduler dying — is caught by the health monitor's check #6.
    # Runs first so it fires even if there are no active users to process.
    try:
        if _log_seen_recently("mergecash-health:", 90) is False:
            _dm_alert(":warning: *MergeCash health monitor looks DOWN* — no `mergecash-health` run logged in the last 90m (flagged by the 4h completion scheduler). The hourly monitor may be stuck — check the `mergecash-health` Scheduler job + the service.")
    except Exception as e:
        logger.warning(f"health-monitor cross-check failed: {e}")

    # 1+2. Stream active users ONCE; expire overdue in Python, collect pending-milestone users.
    # WHY single stream + Python expiry: the old `.where(status==active).where(offer_expires_at<now)`
    # is a 2-filter Firestore query that needs a composite index we never created — it 400'd
    # ("query requires an index") and aborted the entire job before completions were checked
    # (2026-07-28). A single-filter stream needs no index; expiry is a cheap in-memory compare.
    active_docs = fs.collection("users").where("status", "==", "active").stream()
    users = []
    player_ids = set()
    expired_count = 0
    overdue_no_player = []
    for doc in active_docs:
        u = doc.to_dict()
        exp = u.get("offer_expires_at")
        # WHY we no longer expire here (2026-08-03): expiring BEFORE checking chapters meant a player
        # who genuinely earned the reward in their final hours was flipped to 'expired' unpaid — this
        # pass reads the daily rollup, which lags, so "not finished yet" was often just stale data.
        # Overdue users are now carried through the completion check and expired at the END (step 5),
        # and only after we confirm they did not cross their target before the deadline.
        is_overdue = bool(exp and now > exp)
        if not u.get("player_id"):
            # No player_id → nothing to check; expire it here if the window is up.
            if is_overdue:
                doc.reference.update({"status": "expired"})
                expired_count += 1
                overdue_no_player.append(doc.id)
            continue
        found_pending = False
        for m_doc in fs.collection("users").document(doc.id).collection("milestones").where("status", "==", "pending").limit(1).stream():
            found_pending = True
            m = m_doc.to_dict()
            users.append({
                "user_id": doc.id, "player_id": u["player_id"], "email": u["email"],
                "segment": u.get("segment"),
                "milestone_doc_ref": m_doc.reference,
                "target_chapter": m["target_chapter"],
                "reward_amount": m["reward_amount"],
                "checkpoint_chapter": m.get("checkpoint_chapter"),
                "checkpoint_reward_amount": m.get("checkpoint_reward_amount"),
                "user_doc_ref": doc.reference,
                "offer_expires_at": exp,
                "overdue": is_overdue,
            })
            player_ids.add(u["player_id"])
        # WHY: an overdue user with NO pending milestone has nothing to complete, so it never reaches
        # the step-4/5 expiry path — expire it here or it lingers as 'active' forever (regression I
        # introduced by moving expiry later; the old code expired every overdue user up front).
        if is_overdue and not found_pending:
            doc.reference.update({"status": "expired"})
            expired_count += 1

    overdue_n = sum(1 for u in users if u["overdue"])
    logger.info(f"Expired {expired_count} overdue offers; {len(users)} active users with pending "
                f"milestones to check ({overdue_n} of them overdue, checked before expiry)")
    if not users:
        return {"message": "No active users to check", "expired": expired_count, "updated": 0}

    # 3. Batch query max chapters — FRESHEST source, matching get_player_max_chapter() (2026-08-03).
    # WHY the vmp leg: this pass used to read agg_player_chapter_daily ALONE, which only finalizes
    # yesterday. Today's advance was invisible, so completions were detected up to a day late and — in
    # combination with the old expire-first ordering — a player could be expired unpaid despite having
    # earned it. The per-player path (/api/check-progress → get_player_max_chapter) already took the
    # higher of vmp-today vs agg and was verified correct 2026-07-30; this batch path now agrees with it.
    # WHY the 90-day bound on agg: mirrors get_player_max_chapter, and the unbounded form scanned
    # 2.31 GB per run vs 0.62 GB bounded (agg_player_chapter_daily is a VIEW). Safe because every holder
    # of a live offer signed up within ~2 weeks and chapter only ever increases. Both legs are
    # date-partition filtered (org requirement).
    pids_param = list(player_ids)
    rows = bq_query(f"""
        SELECT distinct_id, MAX(CAST(chapter AS INT64)) as max_chapter
        FROM {T('agg_player_chapter_daily')}
        WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
          AND distinct_id IN UNNEST(@pids)
        GROUP BY distinct_id
    """, [bigquery.ArrayQueryParameter("pids", "STRING", pids_param)])
    chapter_map = {r.distinct_id: (r.max_chapter or 0) for r in rows}
    try:
        live_rows = bq_query(f"""
            SELECT distinct_id, MAX(CAST(chapter AS INT64)) as max_chapter
            FROM {T('vmp_master_event_normalized')}
            WHERE date >= CURRENT_DATE() AND chapter IS NOT NULL
              AND distinct_id IN UNNEST(@pids)
            GROUP BY distinct_id
        """, [bigquery.ArrayQueryParameter("pids", "STRING", pids_param)])
        for r in live_rows:
            live = r.max_chapter or 0
            if live > chapter_map.get(r.distinct_id, 0):
                chapter_map[r.distinct_id] = live
    except Exception as e:
        # WHY swallow: the agg leg already succeeded, so degrade to the old (lagging) behaviour rather
        # than aborting the whole completion pass. Log loudly — the health monitor's ERROR scan sees it.
        logger.error(f"verify-all-progress: live chapter leg FAILED, falling back to daily rollup: {e}")

    # 4. Process each user — completion is evaluated BEFORE expiry (see the WHY at step 1+2).
    total_completed = 0
    late_paid = 0
    for u in users:
        max_ch = chapter_map.get(u["player_id"], 0)
        if max_ch > u["target_chapter"]:
            # WHY this gate: an overdue player whose max chapter now exceeds target may have crossed it
            # AFTER their deadline, and max-chapter alone can't say when. Confirm the crossing happened
            # inside the window from vmp event_time before paying — we honour the deadline, we just no
            # longer let rollup lag decide it. Only runs for overdue candidates (normally zero).
            if u["overdue"]:
                if not _crossed_chapter_before_deadline(u["player_id"], u["target_chapter"], u["offer_expires_at"]):
                    u["user_doc_ref"].update({"status": "expired"})
                    expired_count += 1
                    logger.info(f"Expired {u['player_id']} — exceeded target only AFTER the deadline")
                    continue
                late_paid += 1
                logger.info(f"Paying {u['player_id']} — earned before deadline, missed by the rollup lag")

            # Re-check fraud before creating reward
            if check_fraud_status(u["player_id"]):
                fs.collection("users").document(u["user_id"]).update({"status": "fraud_flagged"})
                log_event("fraud_flagged_at_completion", user_id=u["user_id"], player_id=u["player_id"],
                          properties={"source": "scheduler"})
                continue

            # Use transaction to prevent double-reward
            created = complete_milestone_and_create_reward(
                fs, u["user_id"], u["player_id"], u["email"], u["segment"],
                u["milestone_doc_ref"], u["target_chapter"], u["reward_amount"], payout_type="completion"
            )
            if created:
                log_event("milestone_completed_reward_created", user_id=u["user_id"], player_id=u["player_id"],
                          email=u["email"], segment=u["segment"],
                          properties={"reward_amount": u["reward_amount"], "source": "scheduler",
                                      "payout_type": "completion"})
                notify_reward_completed(u["email"], u["player_id"], u["segment"], u["reward_amount"])
                send_completion_email(u["email"], u["reward_amount"], u["target_chapter"])
                total_completed += 1

        # 5. Not finished and past the deadline. MergeCoins players (checkpoint_chapter set) still get
        # the checkpoint reward if they crossed it before the deadline — auto-paid, no player action,
        # per the finalized mechanic (2026-09-09). Non-MergeCoins offers have no checkpoint_chapter, so
        # they fall straight through to plain expiry, unchanged.
        elif u["overdue"]:
            checkpoint_chapter = u.get("checkpoint_chapter")
            if checkpoint_chapter and max_ch > checkpoint_chapter:
                if not _crossed_chapter_before_deadline(u["player_id"], checkpoint_chapter, u["offer_expires_at"]):
                    u["user_doc_ref"].update({"status": "expired"})
                    expired_count += 1
                    logger.info(f"Expired {u['player_id']} — exceeded checkpoint only AFTER the deadline")
                    continue

                if check_fraud_status(u["player_id"]):
                    fs.collection("users").document(u["user_id"]).update({"status": "fraud_flagged"})
                    log_event("fraud_flagged_at_completion", user_id=u["user_id"], player_id=u["player_id"],
                              properties={"source": "scheduler_checkpoint"})
                    continue

                created = complete_milestone_and_create_reward(
                    fs, u["user_id"], u["player_id"], u["email"], u["segment"],
                    u["milestone_doc_ref"], u["target_chapter"], u["checkpoint_reward_amount"],
                    payout_type="checkpoint"
                )
                if created:
                    log_event("milestone_completed_reward_created", user_id=u["user_id"], player_id=u["player_id"],
                              email=u["email"], segment=u["segment"],
                              properties={"reward_amount": u["checkpoint_reward_amount"], "source": "scheduler",
                                          "payout_type": "checkpoint"})
                    notify_reward_completed(u["email"], u["player_id"], u["segment"], u["checkpoint_reward_amount"])
                    send_completion_email(u["email"], u["checkpoint_reward_amount"], u["target_chapter"])
                    total_completed += 1
            else:
                u["user_doc_ref"].update({"status": "expired"})
                expired_count += 1

    logger.info(f"verify-all-progress done: {len(users)} checked, {total_completed} completed "
                f"({late_paid} rescued from rollup lag), {expired_count} expired")
    return {"message": f"Verified {len(users)} users, {total_completed} completed",
            "expired": expired_count, "late_paid": late_paid}


def _dm_alert(text):
    """DM the alert user via the monitor bot token (support_ticket_invest — has im:write)."""
    if not MONITOR_BOT_TOKEN or not ALERT_USER:
        logger.warning("Health alert NOT sent — MERGECASH_MONITOR_BOT_TOKEN / MERGECASH_ALERT_USER not configured")
        return False
    try:
        r = http_requests.post("https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {MONITOR_BOT_TOKEN}"},
            json={"channel": ALERT_USER, "text": text,
                  "username": "MergeCash Monitor", "icon_emoji": ":rotating_light:"}, timeout=10)
        b = r.json()
        if not b.get("ok"):
            logger.error(f"Health alert DM failed: {b.get('error')}")
        return b.get("ok", False)
    except Exception as e:
        logger.error(f"Health alert DM error: {e}")
        return False


def _recent_error_logs(minutes=70):
    """Best-effort scan of this service's ERROR logs via the Logging REST API (metadata token).
    Returns (count, sample_text) or (None, reason) if unavailable (e.g. runtime SA lacks logging read)."""
    try:
        tok = http_requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=5).json()["access_token"]
        start = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
        # WHY the logName restriction (added 2026-08-03): Cloud Run AUDIT logs
        # (cloudaudit.googleapis.com/activity) carry the SAME resource.type and service_name label, so
        # the old filter matched them too. A transient `Services.ReplaceService` code-13 during a routine
        # deploy therefore fired this alert — and because audit entries have no textPayload the DM
        # rendered a useless `• ""`. Every deploy that hit a blip would alert with an empty message.
        # Restrict to the container's own stdout/stderr, which is where logger.error() and tracebacks go.
        # Request-level 5xx are deliberately NOT here — mergecash-5xx-watch covers those in ~10 min.
        flt = ('resource.type="cloud_run_revision" '
               'AND resource.labels.service_name="mergecash-api" '
               f'AND logName=("projects/{PROJECT_ID}/logs/run.googleapis.com%2Fstderr" '
               f'OR "projects/{PROJECT_ID}/logs/run.googleapis.com%2Fstdout") '
               'AND severity>=ERROR '
               f'AND timestamp>="{start}"')
        r = http_requests.post("https://logging.googleapis.com/v2/entries:list",
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            json={"resourceNames": [f"projects/{PROJECT_ID}"], "filter": flt,
                  "orderBy": "timestamp desc", "pageSize": 20}, timeout=15)
        if r.status_code >= 300:
            return None, f"logging API {r.status_code}"
        # WHY drop empty-message entries: an alert whose body is `""` is unactionable — it tells you
        # something happened but not what. Belt-and-braces alongside the logName filter above.
        real = []
        for e in r.json().get("entries", []):
            msg = (e.get("textPayload") or "").strip()
            if not msg and e.get("jsonPayload"):
                msg = json.dumps(e["jsonPayload"])[:150].strip()
            if not msg:
                continue
            real.append(msg)
        sample = "".join(f"\n• {m[:150]}" for m in real[:3])
        return len(real), sample
    except Exception as e:
        return None, str(e)[:120]


def _log_seen_recently(substr, minutes):
    """True if a log whose textPayload contains `substr` appeared in the last `minutes`;
    False if none seen; None if unavailable (no logging read / API error). Fails safe (None)."""
    try:
        tok = http_requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=5).json()["access_token"]
        start = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
        flt = ('resource.type="cloud_run_revision" AND resource.labels.service_name="mergecash-api" '
               f'AND textPayload:"{substr}" AND timestamp>="{start}"')
        r = http_requests.post("https://logging.googleapis.com/v2/entries:list",
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            json={"resourceNames": [f"projects/{PROJECT_ID}"], "filter": flt, "pageSize": 1}, timeout=15)
        if r.status_code >= 300:
            return None
        return len(r.json().get("entries", [])) > 0
    except Exception:
        return None


def _scheduler_ran_recently(minutes=300):
    """Did the 4h completion scheduler (verify-all-progress) run within `minutes`?"""
    return _log_seen_recently("active users with pending milestones", minutes)


# WHY: player-facing 5xx (esp. 504 gateway-timeout on a cold start) reach the browser as an
# HTML error page. The offerwall client blind-parses every response as JSON, so the player sees
# "Unexpected token '<', <!doctype ... is not valid JSON" and a stuck "Loading your offer..."
# screen (support ticket 2026-08-02, player 69fb513d…). These are REQUEST logs (httpRequest.status),
# not severity>=ERROR payloads, so the ERROR-log scan misses them — this needs its own scan.
# Internal/admin paths are excluded: /api/internal 5xx = scheduler, /api/admin 5xx = operator panel;
# neither is a real player. Returns (count, sample_text) or (None, reason) if logging read is unavailable.
def _recent_user_facing_5xx(minutes=12):
    try:
        tok = http_requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=5).json()["access_token"]
        start = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
        flt = ('resource.type="cloud_run_revision" '
               'AND resource.labels.service_name=("mergecash-web" OR "mergecash-api") '
               'AND httpRequest.status>=500 '
               f'AND timestamp>="{start}"')
        r = http_requests.post("https://logging.googleapis.com/v2/entries:list",
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            json={"resourceNames": [f"projects/{PROJECT_ID}"], "filter": flt,
                  "orderBy": "timestamp desc", "pageSize": 50}, timeout=15)
        if r.status_code >= 300:
            return None, f"logging API {r.status_code}"
        entries = r.json().get("entries", [])
        hits = []
        for e in entries:
            hr = e.get("httpRequest", {}) or {}
            url = hr.get("requestUrl", "") or ""
            # skip operator/scheduler noise — only real player traffic counts
            if "/api/internal" in url or "/api/admin" in url:
                continue
            path = url.split("?", 1)[0]  # drop token/query so we never log a JWT/secret
            hits.append(f"{hr.get('status')} {path}")
        sample = "".join(f"\n• {h}" for h in hits[:5])
        return len(hits), sample
    except Exception as e:
        return None, str(e)[:120]


def _signup_attempt_health(minutes=360):
    """Real signup ATTEMPTS vs successes from Cloud Run request logs.
    WHY this exists: 'zero signups in 3h' measures DEMAND, not breakage — at the mature signup rate
    (0.54/h on 2026-08-03, down from 11.4/h at launch) a random 3h window is empty ~20% of the time,
    so that check false-fired ~4-5x/day. The breakage signature is people ATTEMPTING and NOBODY
    succeeding. WHY not 'any non-2xx': 400/409/410 are legitimate business rejections (ineligible
    player, duplicate signup, expired offer) — 29x 400 and 7x 409 in a normal 5 days. Counting those
    as failures would fire on 2-3 ineligible players. WHY not 5xx: already covered within 10 min by
    mergecash-5xx-watch; this catches the 4xx-shaped breaks it misses (bad reCAPTCHA secret,
    eligibility gate broken) where EVERY attempt is rejected.
    WHY the Mozilla filter: scanners hammer /api/signup directly on the run.app URL — the 2026-08-03
    422 was curl/8.7.1. Real players are browsers. Without this, probes alone could trip the check."""
    try:
        tok = http_requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=5).json()["access_token"]
        start = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
        flt = ('resource.type="cloud_run_revision" '
               'AND resource.labels.service_name="mergecash-api" '
               'AND httpRequest.requestUrl:"/api/signup" '
               f'AND timestamp>="{start}"')
        r = http_requests.post("https://logging.googleapis.com/v2/entries:list",
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            json={"resourceNames": [f"projects/{PROJECT_ID}"], "filter": flt,
                  "orderBy": "timestamp desc", "pageSize": 200}, timeout=15)
        if r.status_code >= 300:
            return None
        attempts = 0
        successes = 0
        statuses = {}
        for e in r.json().get("entries", []):
            hr = e.get("httpRequest", {}) or {}
            if "Mozilla" not in (hr.get("userAgent") or ""):
                continue  # probe/scanner, not a player
            st = hr.get("status")
            attempts += 1
            if st and 200 <= st < 300:
                successes += 1
            statuses[st] = statuses.get(st, 0) + 1
        return {"attempts": attempts, "successes": successes,
                "statuses": ", ".join(f"{k}x{v}" for k, v in sorted(statuses.items(), key=lambda x: str(x[0])))}
    except Exception:
        return None


# WHY: near-real-time (10-min) watcher for the player-facing 5xx above, split out from the hourly
# mergecash-health monitor so a gateway-timeout surfaces in ~10 min instead of up to an hour.
# Own scheduler (mergecash-5xx-watch, */10). DMs the alert user ONLY on a hit. min-instances=1
# (set 2026-08-02) should make these near-zero, so any hit is real signal, not routine cold-start noise.
USER_FACING_5XX_ALERT_THRESHOLD = 1  # DM on the first player-facing 5xx in the window

@app.post("/api/internal/mergecash-5xx-watch")
def mergecash_5xx_watch(request: Request):
    require_internal(request)

    # lookback slightly > cadence (10m) so a 5xx can't slip through the gap between runs;
    # the tiny overlap can double-alert a single error at most, acceptable given how rare they are.
    count, sample = _recent_user_facing_5xx(minutes=12)
    if count is None:
        logger.info(f"mergecash-5xx-watch: skipped — logging unavailable ({sample})")
        return {"status": "skipped", "reason": sample}

    logger.info(f"mergecash-5xx-watch: {'ALERT' if count >= USER_FACING_5XX_ALERT_THRESHOLD else 'ok'} — user_facing_5xx_12m={count}")
    if count >= USER_FACING_5XX_ALERT_THRESHOLD:
        body = (f":rotating_light: *MergeCash — {count} player-facing 5xx in the last 12m*\n\n"
                "Players hitting these get an HTML error page the offerwall shows as "
                "_\"Unexpected token '<' … is not valid JSON\"_ + a stuck \"Loading your offer…\" screen "
                "(usually a Cloud Run cold-start/gateway timeout). Check min-instances + the "
                f"`mergecash-web` service logs.{sample}")
        _dm_alert(body)
        return {"status": "alerted", "count": count}
    return {"status": "ok", "count": count}


@app.post("/api/internal/mergecash-health")
def mergecash_health(request: Request):
    """Hourly health monitor. Runs data + log checks; DMs the alert user ONLY on problems.
    Gated by require_internal (OIDC or INTERNAL_SECRET), same as verify-all-progress. Built after
    the 2026-07-28 silent-email-outage incident so a break surfaces in ~1h instead of never."""
    require_internal(request)

    problems = []
    metrics = {}

    # Check 1 — verify-rate. Matured cohort (2–24h old) should be ~85%+; low = email delivery problem.
    #           Plus an acute check on the last 90m to catch a live outage fast.
    try:
        rows = list(bq_query(f"""
            WITH su AS (
              SELECT user_id, MIN(event_timestamp) ts FROM {T('mergecash_events')}
              WHERE DATE(event_timestamp) >= DATE_SUB(CURRENT_DATE(), INTERVAL 2 DAY) AND event_name='signup'
              GROUP BY user_id
            ),
            ver AS (SELECT DISTINCT user_id FROM {T('mergecash_events')}
                    WHERE DATE(event_timestamp) >= DATE_SUB(CURRENT_DATE(), INTERVAL 2 DAY) AND event_name='email_verified')
            SELECT
              COUNTIF(TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), ts, MINUTE) BETWEEN 120 AND 1440) AS matured,
              COUNTIF(TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), ts, MINUTE) BETWEEN 120 AND 1440 AND user_id IN (SELECT user_id FROM ver)) AS matured_verified,
              COUNTIF(TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), ts, MINUTE) <= 90) AS recent90,
              COUNTIF(TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), ts, MINUTE) <= 90 AND user_id IN (SELECT user_id FROM ver)) AS recent90_verified
            FROM su
        """))[0]
        matured, mver = rows.matured or 0, rows.matured_verified or 0
        recent90, r90v = rows.recent90 or 0, rows.recent90_verified or 0
        metrics["matured_verify_pct"] = round(mver / matured * 100) if matured else None
        metrics["recent90_signups"] = recent90
        if matured >= 20 and (mver / matured) < 0.65:
            problems.append(f":email: *Verify-rate low* — matured cohort (2–24h old) verified {mver}/{matured} = {round(mver/matured*100)}% (expect ~85%+). Likely email-delivery issue (SendGrid quota?).")
        if recent90 >= 15 and (r90v / max(recent90, 1)) < 0.15:
            problems.append(f":rotating_light: *Acute outage?* — {recent90} signed up in the last 90m, only {r90v} verified. Check SendGrid + email logs now.")
    except Exception as e:
        problems.append(f":warning: Verify-rate check errored: {str(e)[:150]}")

    # Check 2 — ERROR logs (SendGrid REJECTED / scheduler failures / crashes)
    err_count, err_info = _recent_error_logs(70)
    if err_count is None:
        metrics["error_logs"] = f"unavailable ({err_info})"
    else:
        metrics["error_logs"] = err_count
        if err_count > 0:
            problems.append(f":x: *{err_count} ERROR log(s)* in the last 70m:{err_info}")

    # Check 3 — completion pipeline sanity (mostly no-op until completions start)
    try:
        metrics["completions_last_3h"] = list(bq_query(f"""
            SELECT COUNT(*) n FROM {T('mergecash_events')}
            WHERE event_name='milestone_completed_reward_created'
              AND TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), event_timestamp, HOUR) <= 3
        """))[0].n
    except Exception as e:
        metrics["completions_last_3h"] = f"check failed: {str(e)[:80]}"

    # Check 4 — eligibility gate not emptied (catastrophic: nobody could sign up, no error thrown)
    try:
        elig = list(bq_query(f"SELECT COUNT(*) n FROM {T('mergecash_player_assignments')}"))[0].n
        metrics["eligible_players"] = elig
        if elig < 100:
            problems.append(f":no_entry: *Eligibility gate near-empty* — only {elig} rows in mergecash_player_assignments (expected ~2,277). If wrong, NOBODY can sign up.")
    except Exception as e:
        problems.append(f":warning: Eligibility-count check errored: {str(e)[:120]}")

    # Check 5 — signup pipeline alive. REWRITTEN 2026-08-03; the old rule was
    #   `popup_impressions_today >= 30 AND signups_in_3h == 0`, calibrated during the launch surge
    #   (274 signups on Jul 28 = 11.4/h, where an empty 3h window was ~impossible). By Aug 3 the rate
    #   had decayed to 0.54/h, making P(zero in any 3h) ≈ 20% → ~4-5 false alerts/day. It fired at
    #   19:00 UTC Aug 3 while the service was provably healthy (players hitting /api/dashboard and
    #   /api/check-progress with 200s throughout, 233 page loads at 18:00, a successful signup at
    #   14:55). Alert fatigue on a payout monitor is the real risk, so it's now two precise arms.
    try:
        imp_today = list(bq_query(f"""
            SELECT COUNT(DISTINCT distinct_id) n FROM {T('vmp_master_event_normalized')}
            WHERE date = CURRENT_DATE() AND CAST(live_ops_id AS INT64) IN (6250,6308)
              AND mp_event_name='impression_promo_popup'
        """))[0].n
        metrics["popup_impressions_today"] = imp_today

        # ARM 1 — BREAKAGE: players are attempting and NOBODY is getting through.
        # Independent of volume, so it cannot false-fire on a quiet period.
        # WHY a 12h window and not 6h: at the mature rate (~0.5 signups/h) 6h only accumulates ~2-3
        # browser attempts, so a TOTAL breakage might never reach the >=5 threshold and would be missed
        # outright — worse than detecting it slowly. 12h yields ~6 attempts, making a full break
        # detectable. WHY not lower the threshold to 3 instead: 3 legitimate rejections in a window is
        # plausible (409 duplicate re-signups run ~1.4/day), which would reintroduce false alarms.
        # Slow-but-certain beats fast-but-noisy here: 5xx breaks are already caught in ~10 min by
        # mergecash-5xx-watch, and a delayed 4xx-break detection costs only a handful of signups
        # against a nearly-saturated pool.
        sh = _signup_attempt_health(720)
        if sh is None:
            metrics["signup_attempts_12h"] = "log read failed"
        else:
            metrics["signup_attempts_12h"] = sh["attempts"]
            metrics["signup_successes_12h"] = sh["successes"]
            if sh["attempts"] >= 5 and sh["successes"] == 0:
                problems.append(
                    f":rotating_light: *Signups are FAILING* — {sh['attempts']} real (browser) signup "
                    f"attempts in 12h and ZERO succeeded (statuses: {sh['statuses']}). Check the "
                    f"reCAPTCHA secret, the eligibility table, and BQ deps.")

        # ARM 2 — DEMAND COLLAPSE, measured against a SELF-TUNING baseline rather than a fixed number.
        # WHY relative: an absolute threshold is guaranteed to go stale as the eligible pool saturates
        # (2,277 eligible, 642 already signed up) — which is exactly how the old rule rotted. Comparing
        # the last 12h to the trailing 7-day average per 12h means the alert de-sensitises itself as the
        # campaign naturally winds down, and never needs re-tuning. The >= 3 floor stops it firing once
        # the programme is genuinely dormant (nothing to alert about).
        d = list(bq_query(f"""
            SELECT
              COUNTIF(event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 12 HOUR)) AS recent12,
              COUNTIF(event_timestamp <  TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 12 HOUR)
                  AND event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 8 DAY)) / 14.0 AS base12
            FROM {T('mergecash_events')}
            WHERE event_name='signup'
              AND DATE(event_timestamp) >= DATE_SUB(CURRENT_DATE(), INTERVAL 9 DAY)
        """))[0]
        metrics["signups_12h"] = d.recent12
        metrics["signups_12h_baseline"] = round(d.base12 or 0, 1)
        if d.recent12 == 0 and (d.base12 or 0) >= 3 and imp_today >= 30:
            problems.append(
                f":chart_with_downwards_trend: *No signups in 12h* — {imp_today} popup impressions today, "
                f"but 0 signups vs a trailing baseline of {round(d.base12,1)} per 12h. Could be demand, "
                f"could be a silent break — check Arm 1 (attempts) and the popup audience.")
    except Exception as e:
        metrics["signup_pipeline_check"] = f"errored: {str(e)[:100]}"

    # Check 6 — completion scheduler alive (runs every 4h; if not seen in 5h it's broken → completions missed)
    ran = _scheduler_ran_recently(300)
    metrics["scheduler_ran_5h"] = ran
    if ran is False:
        problems.append(":alarm_clock: *Completion scheduler hasn't run in 5h* (verify-all-progress). Completions won't be auto-detected.")

    # Check 7 — rewards stuck in pending_approval > 24h (nobody fulfilling)
    try:
        fs = get_fs()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        stuck = sum(1 for d in fs.collection("rewards").where("status", "==", "pending_approval").stream()
                    if (d.to_dict().get("created_at") and d.to_dict()["created_at"] < cutoff))
        metrics["rewards_pending_over_24h"] = stuck
        if stuck > 0:
            problems.append(f":gift: *{stuck} reward(s) pending approval >24h* — fulfill them in the admin panel.")
    except Exception as e:
        metrics["rewards_pending_check"] = f"errored: {str(e)[:100]}"

    # Check 8 — completion↔reward integrity: completions logged but reward docs not created
    try:
        # WHY: window this exactly (not TIMESTAMP_DIFF(...,HOUR)<=24) AND 5 min tighter than the
        # reward-doc side's strict `created_at >= now-24h`. Two boundary bugs it fixes:
        #  (1) integer-HOUR truncation kept a completion event in-window for up to ~1h after its
        #      same-instant reward doc had already dropped out of the exact cutoff → spurious
        #      "1 completion / 0 reward docs" mismatch every time a completion crossed 24h
        #      (false-fired on Angelina's 24.3h-old completion, 2026-07-31).
        #  (2) the reward doc's created_at is captured BEFORE the txn while this event is logged
        #      AFTER it commits, so the doc is always a few seconds OLDER — the 5-min margin keeps
        #      the completion window strictly inside the reward window so counted⇒doc-in-window.
        # DATE guard prunes the partition scan.
        comp24 = list(bq_query(f"""
            SELECT COUNT(*) n FROM {T('mergecash_events')}
            WHERE event_name='milestone_completed_reward_created'
              AND DATE(event_timestamp) >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
              AND event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1435 MINUTE)
        """))[0].n
        fs2 = get_fs()
        cutoff2 = datetime.now(timezone.utc) - timedelta(hours=24)
        rewards24 = sum(1 for d in fs2.collection("rewards").stream()
                        if (d.to_dict().get("created_at") and d.to_dict()["created_at"] >= cutoff2))
        metrics["completions_24h"] = comp24
        metrics["reward_docs_24h"] = rewards24
        if comp24 > rewards24:
            problems.append(f":x: *Completion/reward mismatch* — {comp24} completions logged but only {rewards24} reward docs (24h). Reward creation may be failing.")
    except Exception as e:
        metrics["completion_reward_check"] = f"errored: {str(e)[:100]}"

    # Check 9 — fraud detection freshness (stale table → frauds slip through the gate)
    try:
        age_h = list(bq_query(f"""
            SELECT TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(analysis_timestamp), HOUR) age_h
            FROM {T('potential_fraudsters')}
        """))[0].age_h
        metrics["fraud_table_age_h"] = age_h
        if age_h is not None and age_h > 72:
            problems.append(f":mag: *Fraud detection stale* — potential_fraudsters last refreshed {age_h}h ago (>3d).")
    except Exception as e:
        metrics["fraud_freshness_check"] = f"errored: {str(e)[:100]}"

    # Check 10 — completion-pipeline safety net: is anyone owed a reward that never fired?
    # WHY this exists: nothing else cross-checks BQ chapter truth against Firestore status. A player can
    # satisfy `max_chapter > target_chapter` and sit at 'active' indefinitely if the completion path
    # silently fails (fraud re-check, txn abort, BQ error) — that logs NO completion event and creates
    # NO reward doc, so Checks 7/8 (which compare completions to reward DOCS) are blind to it. Added
    # 2026-08-03 after two players at ch65/target65 needed a manual BQ query to be understood at all.
    # WHY gated to every 4th hour (2026-08-03): the two BQ legs below cost 1.27 GB per run —
    # hourly is 927 GB/mo ($5.27), every 4h is 232 GB/mo ($1.32) for IDENTICAL protection, because
    # this check audits the verify-all-progress scheduler, which itself only runs every 4h. Checking
    # more often than the job you audit buys nothing. Offset to 02/06/10/14/18/22 UTC so it inspects
    # state AFTER the scheduler (which runs at 00/04/08/…) has acted, instead of racing it.
    # The OTHER checks deliberately stay hourly — they are cheap Firestore/log reads, and the acute
    # email-delivery check must catch a SendGrid blackout within the hour (2026-07-28 incident).
    # ?full=1 forces a full run for manual QA at any hour.
    force_full = request.query_params.get("full") == "1"
    run_check10 = force_full or datetime.now(timezone.utc).hour % 4 == 2
    if not run_check10:
        metrics["uncredited_check"] = "skipped — runs 02/06/10/14/18/22 UTC (?full=1 forces)"
    else:
        try:
            fs3 = get_fs()
            now3 = datetime.now(timezone.utc)
            pending3 = []  # (player_id, target_chapter, offer_expires_at)
            for doc in fs3.collection("users").where("status", "==", "active").stream():
                u3 = doc.to_dict()
                pid3 = u3.get("player_id")
                if not pid3:
                    continue
                exp3 = u3.get("offer_expires_at")
                if exp3 and now3 > exp3:
                    continue  # already overdue — the 4h scheduler flips these to 'expired'
                for m3 in (fs3.collection("users").document(doc.id).collection("milestones")
                           .where("status", "==", "pending").limit(1).stream()):
                    pending3.append((pid3, m3.to_dict()["target_chapter"], exp3))
            metrics["active_pending_offers"] = len(pending3)

            if pending3:
                pids3 = list({p[0] for p in pending3})
                # WHY the 90-day bound: mirrors get_player_max_chapter() exactly, and the unbounded form
                # (what the 4h scheduler still uses at ~line 1584) scans 2.31 GB vs 0.62 GB bounded —
                # agg_player_chapter_daily is a VIEW, so an unfiltered scan is expensive. Safe because every
                # holder of a LIVE offer signed up within ~2 weeks and chapter only ever increases.
                agg_map3 = {r.distinct_id: (r.max_chapter or 0) for r in bq_query(f"""
                    SELECT distinct_id, MAX(CAST(chapter AS INT64)) max_chapter
                    FROM {T('agg_player_chapter_daily')}
                    WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
                      AND distinct_id IN UNNEST(@pids)
                    GROUP BY distinct_id
                """, [bigquery.ArrayQueryParameter("pids", "STRING", pids3)])}
                vmp_map3 = {r.distinct_id: (r.max_chapter or 0) for r in bq_query(f"""
                    SELECT distinct_id, MAX(CAST(chapter AS INT64)) max_chapter
                    FROM {T('vmp_master_event_normalized')}
                    WHERE date >= CURRENT_DATE() AND chapter IS NOT NULL
                      AND distinct_id IN UNNEST(@pids)
                    GROUP BY distinct_id
                """, [bigquery.ArrayQueryParameter("pids", "STRING", pids3)])}

                hard3, lag3, near3 = [], [], []
                for pid3, tgt3, exp3 in pending3:
                    agg_ch = agg_map3.get(pid3, 0)
                    fresh_ch = max(agg_ch, vmp_map3.get(pid3, 0))
                    hrs_left = round((exp3 - now3).total_seconds() / 3600, 1) if exp3 else None
                    if agg_ch > tgt3:
                        hard3.append(f"`{pid3}` agg ch{agg_ch} > target {tgt3}")
                    elif fresh_ch > tgt3:
                        lag3.append((pid3, fresh_ch, tgt3, hrs_left))
                    elif fresh_ch == tgt3:
                        near3.append((pid3, tgt3, hrs_left))
                metrics["uncredited_hard"] = len(hard3)
                metrics["uncredited_awaiting_rollup"] = len(lag3)
                metrics["one_chapter_away"] = len(near3)

                if hard3:
                    problems.append(
                        f":money_with_wings: *{len(hard3)} reward(s) EARNED but not credited* — these players "
                        f"already exceed target on the very source the 4h scheduler reads "
                        f"(agg_player_chapter_daily), so it had everything it needed and still didn't pay: "
                        + "; ".join(hard3[:5])
                        + ". Completion path is failing — check the fraud re-check + reward txn logs.")
                # WHY only alert the rollup-lag case when the clock is nearly out: normally the scheduler
                # credits it once agg catches up (<1 day) so it's not worth a DM. But the scheduler EXPIRES
                # overdue offers BEFORE checking chapters (~line 1562) and reads only the lagging rollup, so
                # a player who genuinely earned it in their final hours can be expired unpaid.
                urgent3 = [l for l in lag3 if l[3] is not None and l[3] < 12]
                if urgent3:
                    problems.append(
                        f":stopwatch: *{len(urgent3)} player(s) earned it but may EXPIRE before the daily "
                        f"rollup lands* — "
                        + "; ".join(f"`{p}` fresh ch{f} > target {t}, {h}h left" for p, f, t, h in urgent3[:5])
                        + ". Credit them manually — the 4h scheduler reads the lagging rollup and expires "
                          "overdue offers before it checks chapters.")
        except Exception as e:
            metrics["uncredited_check"] = f"errored: {str(e)[:100]}"

    # NOTE: public-site availability is NOT checked here — the service can't reach the public
    # LB from its VPC egress (and the WAF 403s non-browser requests). It's covered instead by
    # the Cloud Monitoring 5xx alert policy on the mergecash-web Cloud Run service.

    # WHY: log every run (not just problems) so the monitor is self-observable — we can confirm
    # it fired hourly and see metrics, and notice if the monitor itself silently stops.
    logger.info(f"mergecash-health: {'ALERT' if problems else 'ok'} — problems={len(problems)} metrics={json.dumps(metrics)}")
    if problems:
        body = (f":rotating_light: *MergeCash health — {len(problems)} issue(s)*\n\n"
                + "\n\n".join(problems) + f"\n\n_metrics: {json.dumps(metrics)}_")
        _dm_alert(body)
        return {"status": "alerted", "problems": len(problems), "metrics": metrics}
    return {"status": "ok", "metrics": metrics}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
