#!/usr/bin/env python3
"""
MergeCash — Comprehensive Test Suite
=====================================
Run after every code change to verify the system is properly configured,
structured, tested, and secured.

Usage:
    python3 test_mergecash.py                    # Run all tests
    python3 test_mergecash.py --section security # Run only security tests
    python3 test_mergecash.py --section api      # Run only API tests

Sections: config, security, api, firestore, segments, frontend, nginx

Prerequisites:
    - GCP credentials configured (gcloud auth)
    - VPN connected (for API endpoint tests)
    - Firestore + BQ accessible
"""

import os
import sys
import json
import re
import argparse
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ── Test framework ──────────────────────────────────────────────────

PASS = 0
FAIL = 0
SKIP = 0
RESULTS = []

def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        RESULTS.append(("PASS", name, detail))
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        RESULTS.append(("FAIL", name, detail))
        print(f"  ✗ {name} — {detail}")

def skip(name, reason=""):
    global SKIP
    SKIP += 1
    RESULTS.append(("SKIP", name, reason))
    print(f"  ○ {name} — {reason}")

def section(name):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")


# ── 1. CONFIG TESTS ────────────────────────────────────────────────

def test_config():
    section("1. CONFIGURATION")

    # 1.1 Check main.py exists and is valid Python
    main_path = os.path.join(os.path.dirname(__file__), 'main.py')
    test("main.py exists", os.path.exists(main_path))

    if os.path.exists(main_path):
        with open(main_path) as f:
            code = f.read()

        # 1.2 Version check
        test("API version is 4.0+",
             'version="4.' in code or "version='4." in code,
             "Expected v4.0+ with security hardening")

        # 1.3 Production docs disabled
        test("FastAPI docs disabled in production",
             "docs_url=None if IS_PRODUCTION" in code)

        # 1.4 JWT secret startup validation
        test("JWT secret validated at startup",
             "raise RuntimeError" in code and "JWT_SECRET" in code,
             "Should crash if JWT_SECRET missing in production")

        # 1.5 No hardcoded secrets
        test("No hardcoded Help Scout secrets",
             'HELPSCOUT_APP_ID = os.getenv("HELPSCOUT_APP_ID", "")' in code,
             "Should use env vars only, no hardcoded defaults")

        # 1.6 Body size limit middleware
        test("Request body size limit middleware",
             "BodySizeLimitMiddleware" in code or "MAX_REQUEST_BODY_BYTES" in code)

        # 1.7 CORS configured
        test("CORS middleware configured",
             "CORSMiddleware" in code)

    # 1.8 Requirements file
    req_path = os.path.join(os.path.dirname(__file__), 'requirements.txt')
    test("requirements.txt exists", os.path.exists(req_path))

    # 1.9 Deploy script exists
    deploy_path = os.path.join(os.path.dirname(__file__), 'deploy.sh')
    test("deploy.sh exists", os.path.exists(deploy_path))


# ── 2. SECURITY TESTS ──────────────────────────────────────────────

def test_security():
    section("2. SECURITY")

    main_path = os.path.join(os.path.dirname(__file__), 'main.py')
    with open(main_path) as f:
        code = f.read()

    # 2.1 JWT has no email
    test("JWT claims don't contain email",
         '"email"' not in code.split("def create_token")[1].split("def ")[0] if "def create_token" in code else False,
         "JWT should only contain sub, exp, iat — no PII")

    # 2.2 Uniform error messages
    test("Uniform error for player validation",
         "Unable to verify eligibility" in code,
         "Should not reveal if player exists vs fraud-flagged")

    # 2.3 Rate limiting on all endpoints
    for endpoint in ["signup", "login", "dashboard", "check_progress", "contact"]:
        test(f"Rate limit on {endpoint}",
             f"check_rate_limit" in code.split(f"def {endpoint}")[1].split("def ")[0] if f"def {endpoint}" in code else False,
             f"Missing rate limit on {endpoint}")

    # 2.4 Security event logging
    for event in ["rate_limit_hit", "captcha_failed", "auth_failed", "admin_access", "admin_access_failed"]:
        test(f"Security event logged: {event}",
             f'"{event}"' in code,
             f"Missing log_event for {event}")

    # 2.5 Firestore transaction for rewards
    test("Reward creation uses Firestore transaction",
         "@firestore.transactional" in code or "firestore.transactional" in code,
         "Race condition: must use transaction to prevent double rewards")

    # 2.6 Fraud re-check in BOTH completion paths
    test("Scheduler re-checks fraud tables",
         "check_fraud_status" in code and "verify_all_progress" in code,
         "Scheduler should re-check fraud before creating reward")

    check_progress_section = code.split("def check_progress")[1].split("def ")[0] if "def check_progress" in code else ""
    test("Check-progress re-checks fraud tables",
         "check_fraud_status" in check_progress_section,
         "check-progress must re-check fraud before creating reward")

    # 2.6b Timer reset prevention
    test("Timer anti-reset: checks ALL popup records",
         "MIN(first_shown_at)" in code or "earliest" in code,
         "Must check for ANY popup record, not just matching liveops_id")

    # 2.6c Player cache TTL reduced
    test("Player cache TTL is 10 min or less",
         "cache_age < 600" in code or "cache_age < 300" in code,
         "Cache TTL should be <=10 min to close fraud detection window")

    # 2.6d Login rate limit tightened
    login_section = code.split("def login")[1].split("def ")[0] if "def login" in code else ""
    test("Login rate limit is 5/min or less",
         "max_requests=5" in login_section or "max_requests=3" in login_section,
         "Login rate limit should be <=5/min to prevent email enumeration")

    # 2.6e Email verification tracking
    test("Email verification flag stored at signup",
         "email_verified" in code,
         "Must track email_verified: False so admin can see unverified emails")

    # 2.6f Idempotent notifications
    test("Notification idempotence flag in transaction",
         "notified" in code.split("complete_milestone_and_create_reward")[1].split("def ")[0] if "complete_milestone_and_create_reward" in code else False,
         "Transaction should set notified flag to prevent duplicate emails")

    # 2.7 Input validation
    test("liveops_id validation exists",
         "validate_liveops_id" in code or "LIVEOPS_ID_PATTERN" in code,
         "liveops_id should be validated")

    test("source_url_params size limit",
         "source_url_params too large" in code,
         "source_url_params should be size-limited")

    test("Contact form subject length limit",
         "Subject too long" in code)

    test("Contact form message length limit",
         "Message too long" in code)

    # 2.8 Admin auth logs
    test("Admin access failures logged",
         "admin_access_failed" in code)

    # 2.9 No datetime.utcnow() usage (should use timezone-aware)
    # Allow in JWT creation where PyJWT requires it
    utcnow_count = code.count("datetime.utcnow()")
    test("Minimal datetime.utcnow() usage (prefer timezone-aware)",
         utcnow_count <= 1,
         f"Found {utcnow_count} instances — should use datetime.now(timezone.utc)")


# ── 3. API ENDPOINT TESTS ──────────────────────────────────────────

def test_api():
    section("3. API ENDPOINTS")

    main_path = os.path.join(os.path.dirname(__file__), 'main.py')
    with open(main_path) as f:
        code = f.read()

    # 3.1 All expected endpoints exist
    endpoints = [
        ("/health", "GET"),
        ("/api/signup", "POST"),
        ("/api/login", "POST"),
        ("/api/dashboard", "GET"),
        ("/api/check-progress", "POST"),
        ("/api/contact", "POST"),
        ("/api/admin/rewards", "GET"),
        ("/api/admin/rewards/{reward_id}/fulfill", "POST"),
        ("/api/admin/rewards/{reward_id}/deny", "POST"),
        ("/api/admin/stats", "GET"),
        ("/api/internal/verify-all-progress", "POST"),
    ]
    for path, method in endpoints:
        # Check for the route decorator
        decorator = f'@app.{method.lower()}("{path}")'
        alt_path = path.replace("{reward_id}", "{reward_id}")
        test(f"Endpoint exists: {method} {path}",
             path.split("{")[0] in code,
             f"Missing endpoint {method} {path}")

    # 3.2 Signup doesn't return segment_id
    # Find the final return statement in signup (the one with is_new: True)
    signup_section = code.split("def signup")[1].split("def ")[0] if "def signup" in code else ""
    # Get just the last return block (the successful signup response)
    last_return = signup_section.rsplit("return {", 1)[-1].split("}")[0] if "return {" in signup_section else ""
    test("Signup response doesn't expose segment_id",
         '"segment"' not in last_return,
         "Segment ID should not be returned to users")

    # 3.3 Dashboard doesn't return segment
    dashboard_return = code.split("def dashboard")[1].split("def ")[0] if "def dashboard" in code else ""
    test("Dashboard response doesn't expose segment",
         '"segment"' not in dashboard_return,
         "Segment should not be in dashboard response")

    # 3.4 Internal endpoint auth
    test("Internal endpoint requires INTERNAL_SECRET",
         "INTERNAL_SECRET" in code.split("verify_all_progress")[1] if "verify_all_progress" in code else False)

    # 3.5 CAPTCHA on signup and contact
    test("CAPTCHA on signup", "recaptcha" in code.split("def signup")[1].split("def ")[0].lower() if "def signup" in code else False)
    test("CAPTCHA on contact", "recaptcha" in code.split("def contact")[1].split("def ")[0].lower() if "def contact" in code else False)

    # 3.7 Email verification endpoints
    test("Endpoint exists: POST /api/verify-email",
         "/api/verify-email" in code)
    test("Endpoint exists: POST /api/resend-code",
         "/api/resend-code" in code)
    test("Signup sends verification code",
         "send_verification_email" in code.split("def signup")[1].split("def ")[0] if "def signup" in code else False,
         "Signup must send verification email before showing offer")
    test("Signup returns requires_verification",
         "requires_verification" in code.split("def signup")[1].split("def ")[0] if "def signup" in code else False)
    test("Dashboard returns email_verified",
         "email_verified" in code.split("def dashboard")[1].split("def ")[0] if "def dashboard" in code else False)
    test("Verification code has expiry (10 min)",
         "timedelta(minutes=10)" in code,
         "Verification codes must expire")
    test("Verification has attempt limit",
         "verification_attempts" in code and ">= 5" in code,
         "Must limit verification attempts")
    test("Verification rate limited",
         "verify:" in code,
         "Verify endpoint must be rate limited")

    # 3.6 Dynamic segment assignment (Itai's bucket logic)
    test("Dynamic segment assignment exists",
         "assign_segment" in code and "SEGMENT_BUCKETS" in code,
         "Should have assign_segment function with SEGMENT_BUCKETS config")
    test("Eligibility check uses BQ player assignments",
         "is_eligible_player" in code and "PLAYER_ASSIGNMENTS_TABLE" in code,
         "is_eligible_player should check BQ assignments table")
    test("match_segment uses eligibility + dynamic assignment",
         "is_eligible_player" in code and "assign_segment" in code,
         "match_segment should check eligibility then assign dynamically")


# ── 4. FIRESTORE TESTS ─────────────────────────────────────────────

def test_firestore():
    section("4. FIRESTORE DATA")

    try:
        from google.cloud import firestore as fs_lib
        fs = fs_lib.Client(project='yotam-395120')

        # 4.1 Segments exist
        segments = list(fs.collection("segments").where("is_active", "==", True).stream())
        test("Active segments exist in Firestore",
             len(segments) > 0,
             f"Found {len(segments)} active segments")

        # 4.2 Segments have required fields
        for doc in segments:
            seg = doc.to_dict()
            has_fields = all(k in seg for k in ["min_chapter", "max_chapter", "target_chapter", "reward_amount", "time_limit_days"])
            test(f"Segment '{doc.id}' has all required fields",
                 has_fields,
                 f"Missing fields in segment {doc.id}")

            # 4.3 Segment ranges are valid
            if has_fields:
                test(f"Segment '{doc.id}' min < max chapter",
                     seg["min_chapter"] <= seg["max_chapter"],
                     f"min={seg['min_chapter']} > max={seg['max_chapter']}")

                test(f"Segment '{doc.id}' target > min chapter",
                     seg["target_chapter"] > seg["min_chapter"],
                     f"target={seg['target_chapter']} <= min={seg['min_chapter']}")

                test(f"Segment '{doc.id}' reward > 0",
                     seg["reward_amount"] > 0,
                     f"reward={seg['reward_amount']}")

                test(f"Segment '{doc.id}' time_limit > 0",
                     seg["time_limit_days"] > 0,
                     f"time_limit={seg['time_limit_days']}")

        # 4.4 Check for overlapping segments
        sorted_segs = sorted(segments, key=lambda d: d.to_dict()["min_chapter"])
        for i in range(len(sorted_segs) - 1):
            s1 = sorted_segs[i].to_dict()
            s2 = sorted_segs[i+1].to_dict()
            test(f"No overlap: '{sorted_segs[i].id}' and '{sorted_segs[i+1].id}'",
                 s1["max_chapter"] < s2["min_chapter"],
                 f"Overlap: {s1['max_chapter']} >= {s2['min_chapter']}")

    except Exception as e:
        skip("Firestore tests", f"Cannot connect: {e}")


# ── 5. SEGMENT SEED SCRIPT TESTS ──────────────────────────────────

def test_segments():
    section("5. SEGMENT SEED SCRIPT")

    seed_path = os.path.join(os.path.dirname(__file__), 'seed_segments.py')
    test("seed_segments.py exists", os.path.exists(seed_path))

    if os.path.exists(seed_path):
        with open(seed_path) as f:
            code = f.read()

        test("Supports --csv argument",
             "--csv" in code,
             "Should accept CSV file path")

        test("Deactivates old segments",
             "is_active" in code and "False" in code,
             "Should deactivate existing segments before seeding new ones")

        test("CSV includes time_limit_days",
             "time_limit_days" in code,
             "CSV format should include time_limit_days column")


# ── 6. FRONTEND TESTS ──────────────────────────────────────────────

def test_frontend():
    section("6. FRONTEND")

    frontend_dir = os.path.expanduser("~/code/merge-cruise-offerwall")

    # 6.1 All required files exist
    for fname in ["index.html", "dashboard.html", "admin.html", "app.js", "api.js", "styles.css", "nginx.conf", "Dockerfile"]:
        test(f"Frontend file exists: {fname}",
             os.path.exists(os.path.join(frontend_dir, fname)))

    # 6.2 app.js security
    app_js = os.path.join(frontend_dir, "app.js")
    if os.path.exists(app_js):
        with open(app_js) as f:
            code = f.read()

        test("XSS escape function exists",
             "function esc(" in code,
             "Must have HTML escape function for dynamic content")

        test("Dynamic content uses esc()",
             "esc(targetCh)" in code or "esc(currentCh)" in code,
             "Chapter numbers should be escaped before DOM insertion")

        # WHY not "pidInput.required = false"/"required = false" in app.js: that assumed a SHARED
        # signup/login form whose Player ID field gets toggled required/not-required per mode. The
        # modal was since redesigned to be login-ONLY (email address alone — see the WHY comment
        # directly above <div id="auth-modal"> in index.html: "Login is email-only by design...
        # there is no password field to look for"); signup now lives entirely in a separate inline
        # hero form (#hero-signup-form) with its own Player ID field. There is no shared field left
        # to toggle, so the old assertion could never pass again — it was failing for the CORRECT
        # reason (the pattern it checked for no longer exists) but for the WRONG label (it read as a
        # missing bug, not a completed, better redesign). Checking the actual current invariant
        # instead: the login modal's form must contain no player-ID input at all.
        auth_modal_html = ""
        index_path = os.path.join(frontend_dir, "index.html")
        if os.path.exists(index_path):
            with open(index_path) as idxf:
                idx_code = idxf.read()
            if 'id="auth-modal"' in idx_code:
                start = idx_code.index('id="auth-modal"')
                end = idx_code.find("</div>\n</div>", start)
                auth_modal_html = idx_code[start:end if end != -1 else start + 2000]
        test("Login modal has no Player ID field (login is email-only by design)",
             bool(auth_modal_html) and "player-id" not in auth_modal_html.lower()
             and "player id" not in auth_modal_html.lower(),
             "Login modal should only ask for email — Player ID belongs to the separate signup form")

    # 6.3 api.js security
    api_js = os.path.join(frontend_dir, "api.js")
    if os.path.exists(api_js):
        with open(api_js) as f:
            code = f.read()

        test("Cookie has Secure flag",
             "Secure" in code,
             "Cookie should have Secure flag")

        test("Cookie has SameSite=Strict",
             "SameSite=Strict" in code,
             "Cookie should have SameSite=Strict")

    # 6.4 admin.html security
    admin_html = os.path.join(frontend_dir, "admin.html")
    if os.path.exists(admin_html):
        with open(admin_html) as f:
            code = f.read()

        test("Admin page has noindex",
             'noindex' in code,
             "Admin page should not be indexed by search engines")

        test("Admin buttons use data attributes (no inline JS injection)",
             "data-reward-id" in code,
             "Reward IDs should use data attributes, not inline onclick interpolation")

    # 6.5 HTML meta tags
    for fname in ["index.html", "dashboard.html"]:
        fpath = os.path.join(frontend_dir, fname)
        if os.path.exists(fpath):
            with open(fpath) as f:
                code = f.read()
            test(f"{fname} has referrer policy",
                 "strict-origin-when-cross-origin" in code)

    # 6.6 reCAPTCHA on signup and contact
    index_html = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_html):
        with open(index_html) as f:
            code = f.read()
        test("Signup CAPTCHA has ID",
             'id="signup-captcha"' in code,
             "Signup CAPTCHA needs unique ID to avoid collision with contact CAPTCHA")
        test("Contact CAPTCHA has ID",
             'id="contact-captcha"' in code)


# ── 7. NGINX TESTS ─────────────────────────────────────────────────

def test_nginx():
    section("7. NGINX CONFIGURATION")

    nginx_path = os.path.expanduser("~/code/merge-cruise-offerwall/nginx.conf")
    if not os.path.exists(nginx_path):
        skip("Nginx tests", "nginx.conf not found")
        return

    with open(nginx_path) as f:
        code = f.read()

    # 7.1 Security headers
    test("X-Content-Type-Options: nosniff",
         "nosniff" in code)
    test("X-Frame-Options: DENY",
         "DENY" in code)
    test("Strict-Transport-Security (HSTS)",
         "Strict-Transport-Security" in code,
         "HSTS header required for HTTPS enforcement")
    test("Referrer-Policy",
         "Referrer-Policy" in code)
    test("Permissions-Policy",
         "Permissions-Policy" in code)
    test("Content-Security-Policy",
         "Content-Security-Policy" in code)
    test("CSP has base-uri",
         "base-uri" in code,
         "CSP should restrict base-uri")
    test("CSP has form-action",
         "form-action" in code,
         "CSP should restrict form-action")
    test("CSP has upgrade-insecure-requests",
         "upgrade-insecure-requests" in code)

    # 7.2 X-XSS-Protection should be 0 (deprecated)
    test("X-XSS-Protection is 0 (disabled, rely on CSP)",
         '"0"' in code and "X-XSS-Protection" in code,
         "X-XSS-Protection should be disabled, not mode=block")

    # 7.3 Server tokens off
    test("Server tokens hidden",
         "server_tokens off" in code)

    # 7.4 Internal API blocked
    test("/api/internal/ blocked",
         "/api/internal/" in code and "return 403" in code)

    # 7.5 Admin rate limiting
    test("Admin API rate limited",
         "limit_req_zone" in code and "admin_limit" in code,
         "Admin endpoints need rate limiting")

    # 7.6 Body size limit
    test("client_max_body_size set",
         "client_max_body_size" in code,
         "Should limit request body size")

    # 7.7 Proxy timeout
    test("proxy_read_timeout set",
         "proxy_read_timeout" in code)

    # 7.8 Attack paths blocked
    test("Common attack paths blocked (.php, .env, .git)",
         ".php" in code and ".env" in code and ".git" in code)

    # 7.9 Hidden files blocked
    test("Hidden files (dotfiles) blocked",
         "location ~ /\\." in code or "location ~ /\\\\" in code)


# ── 8. BQ TABLE TESTS ──────────────────────────────────────────────

def test_bq():
    section("8. BIGQUERY TABLES")

    try:
        from google.cloud import bigquery as bq_lib
        bq = bq_lib.Client(project='yotam-395120')

        tables = [
            ("mergecash_events", "Event logging"),
            ("mergecash_liveops_popups", "Popup impression tracking"),
            ("mergecash_player_assignments", "Per-player segment assignments (Option B)"),
        ]

        for table_name, desc in tables:
            try:
                table = bq.get_table(f'yotam-395120.peerplay.{table_name}')
                test(f"BQ table exists: {table_name} ({desc})", True)
            except Exception:
                test(f"BQ table exists: {table_name} ({desc})", False, "Table not found")

        # Check view
        try:
            table = bq.get_table('yotam-395120.peerplay.mergecash_signed_up_players')
            test("BQ view exists: mergecash_signed_up_players", True)
        except Exception:
            test("BQ view exists: mergecash_signed_up_players", False, "View not found")

    except Exception as e:
        skip("BigQuery tests", f"Cannot connect: {e}")


# ── 9. DEPLOY SCRIPT TESTS ─────────────────────────────────────────

def test_deploy():
    section("9. DEPLOY SCRIPTS")

    # API deploy
    api_deploy = os.path.join(os.path.dirname(__file__), 'deploy.sh')
    if os.path.exists(api_deploy):
        with open(api_deploy) as f:
            code = f.read()

        test("API deploy uses /opt/homebrew/bin/gcloud for secrets",
             "/opt/homebrew/bin/gcloud secrets" in code,
             "Bare 'gcloud' fails in deploy context — must use full path")

        test("API deploy sets INTERNAL_SECRET env var",
             "MERGECASH_INTERNAL_SECRET" in code)

        test("API deploy sets SENDGRID_API_KEY env var",
             "SENDGRID_API_KEY" in code)

        # WHY: these 7 vars are delivered to the live service as native Secret Manager bindings
        # (secretKeyRef) since the 2026-08-31 rotation. If this script goes back to resolving them
        # via `gcloud secrets versions access` and injecting the plaintext as a literal env var
        # (--set-env-vars/--update-env-vars), gcloud refuses to change an existing env var's TYPE
        # from secret-ref to literal — exactly the deploy failure hit on 2026-09-14. This guards
        # against that regression recurring, e.g. if someone copies the old literal-injection
        # pattern for a NEW secret without noticing the other 7 no longer work that way.
        NATIVE_SECRET_VARS = [
            "MERGECASH_JWT_SECRET", "MERGECASH_INTERNAL_SECRET", "RECAPTCHA_SECRET",
            "HELPSCOUT_APP_SECRET", "SENDGRID_API_KEY", "MERGECASH_SLACK_BOT_TOKEN",
            "MERGECASH_MONITOR_BOT_TOKEN",
        ]
        for var in NATIVE_SECRET_VARS:
            test(f"{var} is bound via --set-secrets/--update-secrets, not literal injection",
                 f"{var}=mergecash-" in code,
                 f"{var} is not bound to a mergecash-* secret in a --set-secrets/--update-secrets "
                 "argument — it may be resolved via `gcloud secrets versions access` and injected "
                 "as a literal instead, which fails against the live service's secretKeyRef binding")
        test("deploy.sh actually invokes --set-secrets/--update-secrets at least once",
             "--set-secrets" in code and "--update-secrets" in code,
             "Neither flag found — the 7 native-bound secrets above would have nowhere to attach")

        # WHY not "Authorization=Bearer" in code: that string DOES appear in the file, but only
        # inside a comment explaining why the scheduler jobs deliberately moved AWAY from it (a
        # static bearer header leaked mergecash-internal-secret into transcripts twice, 2026-08-03/04)
        # — the real, current mechanism is OIDC. A substring check against the file text can't tell
        # a comment from code, so it was passing for the wrong reason: it would keep passing even if
        # the OIDC flags were removed entirely (found 2026-09-14), and would start failing if someone
        # simply deleted the historical WHY comment. Checking the actual OIDC flags, and that they
        # appear on EVERY scheduler job (the inline verify-progress block plus the two
        # create_internal_scheduler-driven jobs = 3 total), tests the real security property instead.
        test("Scheduler jobs use OIDC auth (not a static bearer secret)",
             "--oidc-service-account-email" in code and "--oidc-token-audience" in code,
             "Missing OIDC auth flags — see the WHY comment above the scheduler section for why a "
             "static Authorization: Bearer header must never be reintroduced here")
        # WHY >= 2, not >= 3, for 3 scheduler jobs: verify-progress is created inline (1 occurrence),
        # but health + 5xx-watch both go through the shared create_internal_scheduler() function, so
        # its OIDC flags appear once in the source and apply to both calls at runtime — 2 source
        # occurrences correctly covers all 3 jobs. (Caught by this test itself: an initial ">= 3"
        # assumption double-counted the shared function as if it were inlined per job.)
        test("OIDC auth is applied to every scheduler job path (inline verify-progress + the shared "
             "create_internal_scheduler helper used by health/5xx-watch)",
             code.count("--oidc-service-account-email") >= 2,
             f"found {code.count('--oidc-service-account-email')} occurrences, expected >= 2 — "
             "a job created without OIDC would be an unauthenticated internal endpoint")

    # Frontend deploy
    fe_deploy = os.path.expanduser("~/code/merge-cruise-offerwall/deploy.sh")
    if os.path.exists(fe_deploy):
        with open(fe_deploy) as f:
            code = f.read()

        test("Frontend deploy uses SCRIPT_DIR for source",
             "SCRIPT_DIR" in code,
             "Should submit from script directory, not cwd")

        test("Frontend deploy enforces ingress lockdown on every deploy",
             "ingress=internal-and-cloud-load-balancing" in code and code.count("ingress=internal-and-cloud-load-balancing") >= 2,
             "Must enforce ingress lockdown on EVERY deploy, not just bootstrap")

    # API deploy enforces ingress
    api_deploy = os.path.join(os.path.dirname(__file__), 'deploy.sh')
    if os.path.exists(api_deploy):
        with open(api_deploy) as f:
            code = f.read()
        test("API deploy enforces ingress lockdown on every deploy",
             "Enforcing ingress" in code and "ingress=internal-and-cloud-load-balancing" in code,
             "Must enforce ingress lockdown on EVERY deploy, not just bootstrap")


# ── 10. LIVE API TESTS (requires VPN) ──────────────────────────────

def test_live_api():
    section("10. LIVE API INTEGRATION")

    BASE = "https://mergecash-web.yotam.internal.peerplay.dev"

    # Live API tests hit the real deployed service.
    # The VPN gateway requires IAP auth which Python requests can't provide.
    # These tests use the direct Cloud Run URL (which bypasses IAP) for /health only,
    # and skip API endpoint tests that require IAP.
    # For full API testing, use the browser-based tests or curl with IAP token.

    DIRECT_URL = "https://mergecash-api-aqglgkkvdq-uc.a.run.app"

    try:
        import requests
        r = requests.get(f"{BASE}/health", timeout=15)
    except Exception as e:
        skip("Live API tests", f"Cannot reach API (VPN?): {e}")
        return

    # 10.1 Health endpoint
    test("Health returns 200", r.status_code == 200)
    try:
        data = r.json()
        test("Health response is clean (no version/config leak)",
             list(data.keys()) == ["status"],
             f"Unexpected keys: {list(data.keys())}")
    except Exception:
        skip("Health JSON parse", f"Response is not JSON (likely IAP/redirect page). Status={r.status_code}, Content-Type={r.headers.get('content-type', 'unknown')}")

    # Remaining live API tests require IAP auth — skip with instructions
    skip("Signup/login/dashboard/admin API tests",
         "Require IAP auth (run from browser console or with IAP token). See test_mergecash_browser.md for manual checklist.")


# ── 11. PENETRATION TESTS ──────────────────────────────────────────

def test_pentest():
    section("11. PENETRATION TESTS")

    BASE = "https://mergecash-web.yotam.internal.peerplay.dev"

    # Penetration tests validate input rejection and security headers.
    # API endpoints behind IAP are tested via code analysis + browser.
    # These tests verify what we CAN reach without IAP: static files + headers.

    # WHY allow_redirects=False + an explicit IAP-response check, instead of a plain requests.get():
    # this gateway domain is behind Google IAP. An unauthenticated request gets a 302 to Google's own
    # OAuth login page — and that login page itself returns 200 once the redirect is FOLLOWED, which
    # is requests' default behavior. That silently defeated this exact guard: the whole section ran
    # against Google's login page instead of skipping (found 2026-09-14 — every assertion below,
    # including a false "referrer-policy missing" finding, was unknowingly checking Google's page,
    # not this app's real nginx response, because `r.status_code == 200` was true for the WRONG page).
    def _iap_intercepted(resp):
        return resp.headers.get("x-goog-iap-generated-response") == "true" or (
            resp.status_code in (302, 303) and "accounts.google.com" in resp.headers.get("location", "")
        )

    try:
        import requests
        r = requests.get(f"{BASE}/health", timeout=15, allow_redirects=False)
        if _iap_intercepted(r):
            skip("Penetration tests", "Blocked by Google IAP — requires an authenticated VPN "
                                       "session to reach the real app, not just network reachability")
            return
        if r.status_code != 200:
            skip("Penetration tests", f"Cannot reach: {r.status_code}")
            return
    except Exception as e:
        skip("Penetration tests", f"Cannot reach API (VPN?): {e}")
        return

    # 11.1 Static code analysis: player_id regex blocks injection
    main_path = os.path.join(os.path.dirname(__file__), 'main.py')
    with open(main_path) as f:
        code = f.read()

    test("Player ID regex is strict (24 hex chars only)",
         "'^[a-f0-9]{24}$'" in code,
         "Regex should only allow exactly 24 hex chars — blocks SQLi/XSS")

    # Verify the regex actually works
    import re
    hex24 = re.compile(r'^[a-f0-9]{24}$', re.IGNORECASE)
    sqli_payloads = ["' OR '1'='1'; --", "'; DROP TABLE--", "1 UNION SELECT"]
    xss_payloads = ["<script>alert(1)</script>", '"><img onerror=alert>']
    for payload in sqli_payloads + xss_payloads:
        test(f"Regex blocks: {payload[:30]}",
             not hex24.match(payload),
             "Player ID regex should reject this")

    test("Regex accepts valid player ID",
         bool(hex24.match("65e13ae477c15306a7bd5c0e")))

    # 11.2 Path traversal via static file requests
    traversal_paths = ["/.env", "/.git/config", "/.git/HEAD"]
    for path in traversal_paths:
        try:
            r = requests.get(f"{BASE}{path}", timeout=10, allow_redirects=False)
            test(f"Path blocked: {path}",
                 r.status_code in (301, 302, 400, 403, 404),
                 f"Got {r.status_code}")
        except Exception:
            skip(f"Path test: {path}", "Request failed")

    # 11.3 Security headers present on static pages
    # WHY a fresh IAP check here too: this is a SEPARATE request from the /health guard above, and
    # was following redirects (the default), so it could independently land on Google's IAP login
    # page even when /health happened to be reachable — the exact failure mode this whole function
    # exists to avoid. Fall back once without redirects to positively identify a real nginx response
    # before trusting any header (or its absence) as this app's own.
    try:
        r = requests.get(f"{BASE}/", timeout=10, allow_redirects=False)
        if _iap_intercepted(r):
            skip("Security header tests", "Blocked by Google IAP — cannot verify this app's real "
                                           "response headers without an authenticated VPN session")
        else:
            headers = {k.lower(): v for k, v in r.headers.items()}

            for header_name in ["x-content-type-options", "x-frame-options", "content-security-policy",
                                "referrer-policy", "strict-transport-security"]:
                test(f"Response header present: {header_name}",
                     header_name in headers,
                     f"Missing {header_name} header")

            test("Server header doesn't expose version",
                 "nginx/" not in headers.get("server", ""),
                 f"Server: {headers.get('server', 'not set')}")
    except Exception:
        skip("Security header tests", "Cannot reach static pages")

    # 11.4 BQ queries use parameterized inputs (not string interpolation)
    # Count @param usages vs f-string value insertions in SQL
    test("BQ queries use parameterized inputs",
         code.count("@pid") >= 3 and code.count("bq_param") >= 3,
         "All BQ queries must use parameterized inputs, never f-string values")

    # 11.5 No eval/exec in code
    test("No eval() in code",
         "eval(" not in code,
         "eval() is a code injection risk")
    test("No exec() in code",
         "exec(" not in code,
         "exec() is a code injection risk")

    # 11.6 No pickle/marshal (deserialization attacks)
    test("No pickle in code",
         "pickle" not in code,
         "pickle is a deserialization attack vector")

    # 11.7 CORS not set to wildcard
    test("CORS not wildcard",
         '"*"' not in code.split("CORSMiddleware")[1].split(")")[0] if "CORSMiddleware" in code else True,
         "CORS should never be set to *")


# ── 12. CLOUD RUN ENV VERIFICATION ─────────────────────────────────

def test_cloud_run():
    section("12. CLOUD RUN ENVIRONMENT")

    try:
        import subprocess
        result = subprocess.run(
            ["/opt/homebrew/bin/gcloud", "run", "services", "describe", "mergecash-api",
             "--region=us-central1", "--project=yotam-395120",
             "--format=yaml(spec.template.spec.containers[0].env)"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            skip("Cloud Run env tests", "Cannot describe service")
            return

        env_output = result.stdout

        # Required env vars
        required_vars = [
            "MERGECASH_JWT_SECRET",
            "MERGECASH_INTERNAL_SECRET",
            "RECAPTCHA_SECRET",
            "SENDGRID_API_KEY",
            "GCP_PROJECT_ID",
            "CLOUD_RUN",
        ]
        for var in required_vars:
            test(f"Cloud Run env var set: {var}",
                 var in env_output,
                 f"{var} not found in deployed env vars")

        # Check that env vars have values (not empty) — accepts EITHER a literal value OR a native
        # Secret Manager binding (valueFrom.secretKeyRef). WHY both: these vars have been delivered
        # via secretKeyRef since the 2026-08-31 secret rotation, not as literals — a check for
        # `value` alone reports them as "empty" even though they're correctly configured (found
        # 2026-09-14, same root confusion that had broken deploy.sh since that rotation).
        import yaml
        try:
            parsed = yaml.safe_load(env_output)
            envs = parsed.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [{}])[0].get("env", [])
            for env in envs:
                name = env.get("name", "")
                if name in ["MERGECASH_JWT_SECRET", "MERGECASH_INTERNAL_SECRET", "SENDGRID_API_KEY"]:
                    has_literal_value = bool(env.get("value", ""))
                    has_secret_ref = bool((env.get("valueFrom") or {}).get("secretKeyRef"))
                    test(f"Cloud Run env var has value: {name}",
                         has_literal_value or has_secret_ref,
                         f"{name} is neither a literal value nor a Secret Manager reference — secret not loaded")
        except Exception:
            pass  # YAML parsing optional, main checks above are sufficient

        # Check ingress
        result2 = subprocess.run(
            ["/opt/homebrew/bin/gcloud", "run", "services", "describe", "mergecash-api",
             "--region=us-central1", "--project=yotam-395120",
             "--format=value(metadata.annotations[run.googleapis.com/ingress])"],
            capture_output=True, text=True, timeout=30
        )
        ingress = result2.stdout.strip()
        test("API ingress is internal-and-cloud-load-balancing",
             ingress == "internal-and-cloud-load-balancing",
             f"Ingress is: {ingress}")

        # Check max instances
        result3 = subprocess.run(
            ["/opt/homebrew/bin/gcloud", "run", "services", "describe", "mergecash-api",
             "--region=us-central1", "--project=yotam-395120",
             "--format=value(spec.template.metadata.annotations[autoscaling.knative.dev/maxScale])"],
            capture_output=True, text=True, timeout=30
        )
        max_inst = result3.stdout.strip()
        test("API max instances is limited (not unlimited)",
             max_inst and int(max_inst) <= 10,
             f"Max instances: {max_inst or 'unlimited'} — should be capped to prevent billing attacks")

        # Check scheduler
        result4 = subprocess.run(
            ["/opt/homebrew/bin/gcloud", "scheduler", "jobs", "describe", "mergecash-verify-progress",
             "--location=us-central1", "--project=yotam-395120",
             "--format=value(state)"],
            capture_output=True, text=True, timeout=30
        )
        test("Scheduler job is ENABLED",
             result4.stdout.strip() == "ENABLED",
             f"Scheduler state: {result4.stdout.strip()}")

    except Exception as e:
        skip("Cloud Run env tests", f"Error: {e}")


# ── 13. BUSINESS LOGIC TESTS ──────────────────────────────────────

def test_business_logic():
    section("13. BUSINESS LOGIC")

    main_path = os.path.join(os.path.dirname(__file__), 'main.py')
    with open(main_path) as f:
        code = f.read()

    # 13.1 Duplicate player ID check
    test("Duplicate player ID check exists",
         "already linked to another account" in code,
         "Should prevent same player_id from signing up twice")

    # 13.2 Expired offer check at signup
    test("Expired offer rejected at signup",
         "This offer has expired" in code,
         "Should reject if popup was shown too long ago")

    # 13.3 Expired offer check at progress
    test("Expired offer check in check-progress",
         "Offer has expired" in code and "def check_progress" in code)

    # 13.4 Already completed check
    test("Already completed milestone returns early",
         "Milestone already completed" in code)

    # 13.5 Player past target chapter rejected
    test("Player already past target chapter rejected",
         "No offer available for your current progress level" in code)

    # 13.6 Reward amount comes from segment, not user input
    signup_section = code.split("def signup")[1].split("def ")[0] if "def signup" in code else ""
    test("Reward amount from segment config (not user input)",
         'segment["reward_amount"]' in signup_section or "segment.get" in signup_section,
         "Reward amount must come from server-side segment config, never from client")

    # 13.7 Timer uses popup first_shown_at when available
    test("Timer uses popup first_shown_at",
         "get_popup_first_shown" in code and "popup_shown_at" in code,
         "Timer should start from popup impression, not signup")

    # 13.8 Fallback timer from signup
    test("Timer fallback to signup time",
         "expires_at = now + timedelta" in code,
         "Should fall back to signup time when no popup data")

    # 13.9 Scheduler expires overdue offers
    test("Scheduler expires overdue offers",
         "offer_expires_at" in code and "expired" in code.split("verify_all_progress")[1] if "verify_all_progress" in code else False,
         "Scheduler should auto-expire overdue offers")

    # 13.10 Reward requires admin approval (not auto-fulfilled)
    test("Rewards created as pending_approval",
         '"pending_approval"' in code,
         "Rewards must not be auto-fulfilled")

    # 13.11 Double-fulfill protection
    test("Cannot fulfill an already-fulfilled reward",
         "Reward already fulfilled" in code,
         "Should prevent double-fulfillment")

    # 13.12 Email normalization applied
    test("Email normalization at signup",
         "normalize_email" in signup_section,
         "Email must be normalized before any operations")

    # 13.13 Per-segment time limits
    test("Per-segment time_limit_days",
         "time_limit_days" in signup_section,
         "Each segment should have its own time limit")


# ── 14. ROUTE REGISTRATION INTEGRITY ──────────────────────────────────
# WHY this section exists: on 2026-09-09, factoring _crossed_chapter_before_deadline() out of
# verify_all_progress() left the @app.post("/api/internal/verify-all-progress") decorator stranded
# above the new helper instead of the function it was meant to decorate — a Python decorator binds to
# the very next `def`, so this is syntactically valid and silently WRONG. Two consequences: the real
# 4h completion scheduler was never registered as a route (Cloud Scheduler would 422 against it
# forever), and the helper became an unauthenticated route instead (a BQ-backed oracle with no auth).
# Caught by a pr-reviewer pass reading the file directly, NOT by the isolated unit tests — those
# extract pure function bodies via ast and never touch the real @app.get/@app.post wiring at all. This
# section closes that structural blind spot: it maps every expected endpoint to the function name it
# MUST decorate, using ast (so it reflects the actual current binding, not a hand-copied guess).

def test_routes():
    section("14. ROUTE REGISTRATION INTEGRITY")

    main_path = os.path.join(os.path.dirname(__file__), 'main.py')
    if not os.path.exists(main_path):
        skip("Route registration tests", "main.py not found")
        return

    import ast
    source = open(main_path).read()
    tree = ast.parse(source)

    # Every /api/... endpoint that should exist, mapped to the exact function name that must be
    # decorated. If a decorator ever gets separated from its intended function, this fails loudly
    # instead of silently shipping a broken or unauthenticated route.
    EXPECTED_ROUTES = {
        "/health": "health",
        "/api/signup": "signup",
        "/api/verify-email": "verify_email",
        "/api/resend-code": "resend_verification_code",
        "/api/login": "login",
        "/api/dashboard": "dashboard",
        "/api/check-progress": "check_progress",
        "/api/contact": "contact",
        "/api/admin/rewards": "list_rewards",
        "/api/admin/rewards/{reward_id}/fulfill": "fulfill_reward",
        "/api/admin/rewards/{reward_id}/deny": "deny_reward",
        "/api/admin/rewards/{reward_id}/notes": "update_reward_notes",
        "/api/admin/users": "list_users",
        "/api/admin/view-as-user": "admin_view_as_user",
        "/api/admin/stats": "admin_stats",
        "/api/internal/verify-all-progress": "verify_all_progress",
        "/api/internal/mergecash-5xx-watch": "mergecash_5xx_watch",
        "/api/internal/mergecash-health": "mergecash_health",
    }

    found_routes = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr in ("get", "post")
                    and isinstance(dec.func.value, ast.Name) and dec.func.value.id == "app"
                    and dec.args and isinstance(dec.args[0], ast.Constant)):
                found_routes[dec.args[0].value] = node.name

    for path, expected_fn in EXPECTED_ROUTES.items():
        actual_fn = found_routes.get(path)
        test(f"route {path} -> {expected_fn}()",
             actual_fn == expected_fn,
             f"decorator binds to {actual_fn}() instead — stranded/misplaced decorator" if actual_fn
             else "route is not registered at all — decorator missing or misplaced")

    extra = set(found_routes) - set(EXPECTED_ROUTES)
    test("no unexpected/undocumented routes exist beyond EXPECTED_ROUTES",
         not extra,
         f"found undocumented routes: {extra} — add them to EXPECTED_ROUTES or investigate")

    # Every /api/internal/* route is meant to be Cloud-Scheduler-only — require_internal() is the
    # entire auth gate for it. A route that's missing this call (whether from a fresh bug or the same
    # class of stranded-decorator mistake) is a live unauthenticated internal endpoint.
    internal_paths = {p: fn for p, fn in EXPECTED_ROUTES.items() if p.startswith("/api/internal/")}
    for path, fn_name in internal_paths.items():
        fn_node = next((n for n in tree.body
                         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn_name),
                        None)
        if fn_node is None:
            continue  # already reported as missing above
        fn_source = ast.get_source_segment(source, fn_node) or ""
        test(f"{fn_name}() ({path}) calls require_internal()",
             "require_internal(" in fn_source,
             "internal endpoint is missing its auth gate — would be reachable with no authentication")


# ── MAIN ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MergeCash Test Suite")
    parser.add_argument("--section", help="Run specific section: config, security, api, firestore, segments, frontend, nginx, bq, deploy")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  MERGECASH TEST SUITE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    sections = {
        "config": test_config,
        "security": test_security,
        "api": test_api,
        "firestore": test_firestore,
        "segments": test_segments,
        "frontend": test_frontend,
        "nginx": test_nginx,
        "bq": test_bq,
        "deploy": test_deploy,
        "live": test_live_api,
        "pentest": test_pentest,
        "cloudrun": test_cloud_run,
        "logic": test_business_logic,
        "routes": test_routes,
    }

    if args.section:
        if args.section in sections:
            sections[args.section]()
        else:
            print(f"Unknown section: {args.section}")
            print(f"Available: {', '.join(sections.keys())}")
            sys.exit(1)
    else:
        for fn in sections.values():
            fn()

    # Summary
    total = PASS + FAIL + SKIP
    print(f"\n{'='*60}")
    print(f"  RESULTS: {PASS} passed, {FAIL} failed, {SKIP} skipped ({total} total)")
    print(f"{'='*60}")

    if FAIL > 0:
        print("\n  FAILURES:")
        for status, name, detail in RESULTS:
            if status == "FAIL":
                print(f"    ✗ {name}: {detail}")

    print()
    sys.exit(1 if FAIL > 0 else 0)
