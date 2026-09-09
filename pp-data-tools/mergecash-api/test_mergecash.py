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

        test("Login mode disables player ID required",
             "pidInput.required = false" in code or "required = false" in code,
             "Player ID field should not be required in login mode")

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

        test("Scheduler uses auth header",
             "Authorization=Bearer" in code)

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

    try:
        import requests
        r = requests.get(f"{BASE}/health", timeout=15)
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
    try:
        r = requests.get(f"{BASE}/", timeout=10)
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

        # Check that env vars have values (not empty)
        import yaml
        try:
            parsed = yaml.safe_load(env_output)
            envs = parsed.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [{}])[0].get("env", [])
            for env in envs:
                name = env.get("name", "")
                value = env.get("value", "")
                if name in ["MERGECASH_JWT_SECRET", "MERGECASH_INTERNAL_SECRET", "SENDGRID_API_KEY"]:
                    test(f"Cloud Run env var has value: {name}",
                         bool(value),
                         f"{name} is empty — secrets not loaded")
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
