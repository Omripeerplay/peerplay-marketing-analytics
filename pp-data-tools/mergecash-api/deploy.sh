#!/bin/bash
# =============================================================================
# MERGECASH API DEPLOY — behind internal VPC + cloudrun-gateway (Harmony SASE VPN)
# =============================================================================
# Deployed PRIVATE inside the `internal` VPC, reachable ONLY through the
# cloudrun-gateway LB at mergecash-api.yotam.internal.peerplay.dev
# (over Harmony SASE VPN). IAP is handled by the gateway — DO NOT enable IAP
# on this service directly.
#
# First deploy: ./deploy.sh --bootstrap
# Normal redeploy: ./deploy.sh
# =============================================================================

set -e

SERVICE_NAME="mergecash-api"
REGION="us-central1"
PROJECT="yotam-395120"
VPC_NETWORK="internal"
VPC_SUBNET="internal-egress"
GATEWAY_DOMAIN="internal.peerplay.dev"
SERVICE_ACCOUNT="bigquery-alerts-to-slack@yotam-395120.iam.gserviceaccount.com"
IMAGE="us-central1-docker.pkg.dev/${PROJECT}/cloud-run-source-deploy/${SERVICE_NAME}:latest"

BOOTSTRAP=0
for arg in "$@"; do
  case "$arg" in
    --bootstrap) BOOTSTRAP=1 ;;
  esac
done

echo ""
echo "Deploying: $SERVICE_NAME"
echo "  Project: $PROJECT  Region: $REGION"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── 1. Prepare build context ──────────────────────────────────────────
BUILD_DIR=$(mktemp -d)
cp "$SCRIPT_DIR/requirements.txt" "$BUILD_DIR/"
cp "$SCRIPT_DIR/main.py" "$BUILD_DIR/"
mkdir -p "$BUILD_DIR/shared"
cp "$PARENT_DIR/shared/__init__.py" "$BUILD_DIR/shared/"
cp "$PARENT_DIR/shared/config.py" "$BUILD_DIR/shared/"
cp "$PARENT_DIR/shared/slack_client.py" "$BUILD_DIR/shared/"

cat > "$BUILD_DIR/Dockerfile" << 'DOCKERFILE'
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY shared/ /app/shared/
COPY main.py /app/main.py
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
DOCKERFILE

cat > "$BUILD_DIR/cloudbuild.yaml" << 'CLOUDBUILD'
steps:
  - name: 'gcr.io/kaniko-project/executor:latest'
    args:
      - --destination=us-central1-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/${_SERVICE}:$BUILD_ID
      - --destination=us-central1-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/${_SERVICE}:latest
      - --cache=true
      - --cache-ttl=720h
      - --cache-repo=us-central1-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/${_SERVICE}/cache
      - --dockerfile=Dockerfile
      - --context=dir:///workspace
      - --snapshot-mode=redo
      - --use-new-run
options:
  # WHY no machineType pin: E2_HIGHCPU_8 had no capacity in us-central1 on 2026-08-03 — a build sat
  # QUEUED 45+ min as the ONLY build in the project (queueTtl is 3600s, so it would have died without
  # ever starting), blocking a deploy entirely. The default pool is what mergecash-web already uses and
  # it starts immediately. Kaniko layer caching keeps the build fast without the bigger machine.
  # If you re-pin a machineType, expect deploys to hang whenever that type is capacity-constrained.
  logging: CLOUD_LOGGING_ONLY
substitutions:
  _SERVICE: 'mergecash-api'
timeout: 1200s
CLOUDBUILD

cd "$BUILD_DIR"

# ── 2. Build via Cloud Build ──────────────────────────────────────────
echo "→ Submitting build..."
/opt/homebrew/bin/gcloud builds submit \
  --project="$PROJECT" \
  --config=cloudbuild.yaml \
  --substitutions=_SERVICE="$SERVICE_NAME" \
  --quiet

# ── 2b. Pre-flight: secrets that MUST be non-empty ───────────────────
# WHY: every secret below is fetched inline with `|| echo ''`, and this script has no `set -e`, so a
# Secret Manager read failure silently ships an EMPTY value. That is exactly how CAPTCHA verification
# stayed off from launch until 2026-08-04 (secret didn't exist → RECAPTCHA_SECRET='' → both call sites
# `if recaptcha_secret:` skipped verification). main.py now refuses to boot on an empty
# RECAPTCHA_SECRET, but failing HERE is better: it costs 2 seconds and tells you which secret, instead
# of a confusing container-startup crash after a full build+deploy cycle.
for _req_secret in mergecash-jwt-secret mergecash-internal-secret mergecash-recaptcha-secret; do
  if ! /opt/homebrew/bin/gcloud secrets versions access latest --secret="$_req_secret" \
        --project="$PROJECT" >/dev/null 2>&1; then
    echo ""
    echo "✗ ABORTING: required secret '$_req_secret' is missing or unreadable in project $PROJECT."
    echo "  Deploying anyway would ship an empty value and silently disable what it protects."
    exit 1
  fi
done
echo "→ Pre-flight OK: required secrets readable"

# ── 3. Deploy to Cloud Run (VPN-only) ────────────────────────────────
echo "→ Deploying to Cloud Run..."

# Scheduler OIDC identity + audience must be baked into the API's env so require_internal() can
# verify the id_token. Resolved BEFORE the deploy (the service already exists and its run.app URL
# is stable) because the post-deploy SERVICE_URL lookup happens too late for --set-env-vars.
SCHEDULER_SA_ENV="bigquery-alerts-to-slack@${PROJECT}.iam.gserviceaccount.com"
OIDC_AUD_ENV=$(/opt/homebrew/bin/gcloud run services describe "$SERVICE_NAME" --region="$REGION" --project="$PROJECT" --format="value(status.url)" 2>/dev/null || echo '')
# SSO (admin panel) — DELIBERATELY DIFFERENT VALUES from the scheduler OIDC above.
# The cloudrun-gateway authenticates to the mergecash-WEB service (nginx) and forwards the original
# Authorization header to this API, so its token's audience is the WEB url, not the API url. Verified
# by measurement 2026-08-04; using the API url here rejects every request with InvalidValue.
SSO_AUD_ENV=$(/opt/homebrew/bin/gcloud run services describe mergecash-web --region="$REGION" --project="$PROJECT" --format="value(status.url)" 2>/dev/null || echo '')
SSO_GW_SA_ENV="cloudrun-gateway-sa@${PROJECT}.iam.gserviceaccount.com"
OIDC_ENV_PAIRS="||MERGECASH_SCHEDULER_SA=${SCHEDULER_SA_ENV}||MERGECASH_OIDC_AUDIENCE=${OIDC_AUD_ENV}||MERGECASH_SSO_AUDIENCE=${SSO_AUD_ENV}||MERGECASH_SSO_GATEWAY_SA=${SSO_GW_SA_ENV}||MERGECASH_SSO_DOMAIN=peerplay.com"

if [ $BOOTSTRAP -eq 1 ] || ! /opt/homebrew/bin/gcloud run services describe "$SERVICE_NAME" --region="$REGION" --project="$PROJECT" >/dev/null 2>&1; then
  echo "  (bootstrap mode — setting VPC/ingress)"
  /opt/homebrew/bin/gcloud run deploy "$SERVICE_NAME" \
    --image "$IMAGE" \
    --region "$REGION" --project "$PROJECT" \
    --service-account "$SERVICE_ACCOUNT" \
    --allow-unauthenticated \
    --ingress=internal-and-cloud-load-balancing \
    --network="$VPC_NETWORK" --subnet="$VPC_SUBNET" --vpc-egress=all-traffic \
    --memory 512Mi --cpu 1 --timeout 300 --max-instances 3 \
    --set-env-vars "^||^GCP_PROJECT_ID=$PROJECT||CLOUD_RUN=true||MERGECASH_JWT_SECRET=$(/opt/homebrew/bin/gcloud secrets versions access latest --secret=mergecash-jwt-secret --project=$PROJECT)||MERGECASH_INTERNAL_SECRET=$(/opt/homebrew/bin/gcloud secrets versions access latest --secret=mergecash-internal-secret --project=$PROJECT)||RECAPTCHA_SECRET=$(/opt/homebrew/bin/gcloud secrets versions access latest --secret=mergecash-recaptcha-secret --project=$PROJECT 2>/dev/null || echo '')||MERGECASH_SLACK_WEBHOOK=$(/opt/homebrew/bin/gcloud secrets versions access latest --secret=mergecash-slack-webhook --project=$PROJECT 2>/dev/null || echo '')||MERGECASH_SLACK_BOT_TOKEN=$(/opt/homebrew/bin/gcloud secrets versions access latest --secret=aso-slack-bot-token --project=$PROJECT 2>/dev/null || echo '')||MERGECASH_SLACK_CHANNEL=C0B7KG75BRN||MERGECASH_MONITOR_BOT_TOKEN=$(/opt/homebrew/bin/gcloud secrets versions access latest --secret=aso-slack-bot-token --project=$PROJECT 2>/dev/null || echo '')||MERGECASH_ALERT_USER=U05V9L9K2QK||HELPSCOUT_APP_ID=$(/opt/homebrew/bin/gcloud secrets versions access latest --secret=helpscout-client-id --project=$PROJECT 2>/dev/null || echo '')||HELPSCOUT_APP_SECRET=$(/opt/homebrew/bin/gcloud secrets versions access latest --secret=helpscout-client-secret --project=$PROJECT 2>/dev/null || echo '')||HELPSCOUT_MAILBOX_ID=337204||SENDGRID_API_KEY=$(/opt/homebrew/bin/gcloud secrets versions access latest --secret=sendgrid-api-key --project=$PROJECT 2>/dev/null || echo '')${OIDC_ENV_PAIRS}" \
    --quiet
else
  # Update image + refresh secrets from Secret Manager on every deploy
  /opt/homebrew/bin/gcloud run services update "$SERVICE_NAME" \
    --image "$IMAGE" \
    --region "$REGION" --project "$PROJECT" \
    --update-env-vars "^||^MERGECASH_JWT_SECRET=$(/opt/homebrew/bin/gcloud secrets versions access latest --secret=mergecash-jwt-secret --project=$PROJECT)||MERGECASH_INTERNAL_SECRET=$(/opt/homebrew/bin/gcloud secrets versions access latest --secret=mergecash-internal-secret --project=$PROJECT)||RECAPTCHA_SECRET=$(/opt/homebrew/bin/gcloud secrets versions access latest --secret=mergecash-recaptcha-secret --project=$PROJECT 2>/dev/null || echo '')||MERGECASH_SLACK_WEBHOOK=$(/opt/homebrew/bin/gcloud secrets versions access latest --secret=mergecash-slack-webhook --project=$PROJECT 2>/dev/null || echo '')||MERGECASH_SLACK_BOT_TOKEN=$(/opt/homebrew/bin/gcloud secrets versions access latest --secret=aso-slack-bot-token --project=$PROJECT 2>/dev/null || echo '')||MERGECASH_SLACK_CHANNEL=C0B7KG75BRN||MERGECASH_MONITOR_BOT_TOKEN=$(/opt/homebrew/bin/gcloud secrets versions access latest --secret=aso-slack-bot-token --project=$PROJECT 2>/dev/null || echo '')||MERGECASH_ALERT_USER=U05V9L9K2QK||HELPSCOUT_APP_ID=$(/opt/homebrew/bin/gcloud secrets versions access latest --secret=helpscout-client-id --project=$PROJECT 2>/dev/null || echo '')||HELPSCOUT_APP_SECRET=$(/opt/homebrew/bin/gcloud secrets versions access latest --secret=helpscout-client-secret --project=$PROJECT 2>/dev/null || echo '')||HELPSCOUT_MAILBOX_ID=337204||SENDGRID_API_KEY=$(/opt/homebrew/bin/gcloud secrets versions access latest --secret=sendgrid-api-key --project=$PROJECT 2>/dev/null || echo '')${OIDC_ENV_PAIRS}" \
    --quiet
fi

# Clean up
rm -rf "$BUILD_DIR"

# ── Always enforce ingress lockdown (prevents silent reopening) ────
echo "→ Enforcing ingress=internal-and-cloud-load-balancing..."
/opt/homebrew/bin/gcloud run services update "$SERVICE_NAME" \
  --region "$REGION" --project "$PROJECT" \
  --ingress=internal-and-cloud-load-balancing \
  --quiet 2>/dev/null || true

SERVICE_URL=$(/opt/homebrew/bin/gcloud run services describe "$SERVICE_NAME" --region="$REGION" --project="$PROJECT" --format="value(status.url)")
GATEWAY_URL="https://${SERVICE_NAME}.yotam.${GATEWAY_DOMAIN}"

echo ""
echo "========================================================================"
echo "DEPLOYMENT SUCCESSFUL"
echo "========================================================================"
echo "  VPN URL  : $GATEWAY_URL  (Harmony SASE VPN required)"
echo "  Internal : $SERVICE_URL"
echo ""

# ── 4. Cloud Scheduler ────────────────────────────────────────────────
# AUTH = OIDC, not a static bearer secret.
# WHY: --headers="Authorization=Bearer <secret>" stores the secret in PLAINTEXT in the job config,
# where `gcloud scheduler jobs describe` exposes it AND `jobs create` echoes it to stdout — which
# leaked it into Claude Code transcripts twice (2026-08-03, 2026-08-04). With OIDC, Cloud Scheduler
# mints a short-lived Google-signed id_token per run and nothing secret is stored anywhere.
# The API verifies it in require_internal() (SA + audience must both match).
# Output of every create is sent to /dev/null regardless — belt and braces, so a future auth change
# can't silently start printing credentials again.
SCHEDULER_JOB_NAME="mergecash-verify-progress"
SCHEDULER_SA="bigquery-alerts-to-slack@${PROJECT}.iam.gserviceaccount.com"

# Delete + recreate (gcloud scheduler update doesn't support changing auth mode cleanly)
if /opt/homebrew/bin/gcloud scheduler jobs describe "$SCHEDULER_JOB_NAME" --location="$REGION" --project="$PROJECT" &>/dev/null; then
    echo "Recreating scheduler job (to update auth/config)..."
    /opt/homebrew/bin/gcloud scheduler jobs delete "$SCHEDULER_JOB_NAME" --location="$REGION" --project="$PROJECT" --quiet
fi

/opt/homebrew/bin/gcloud scheduler jobs create http "$SCHEDULER_JOB_NAME" \
  --location="$REGION" \
  --schedule="0 */4 * * *" \
  --uri="$SERVICE_URL/api/internal/verify-all-progress" \
  --http-method=POST \
  --time-zone="UTC" \
  --attempt-deadline=300s \
  --project="$PROJECT" \
  --oidc-service-account-email="$SCHEDULER_SA" \
  --oidc-token-audience="$SERVICE_URL" >/dev/null

echo ""
echo "Scheduler: every 4h → $SERVICE_URL/api/internal/verify-all-progress (OIDC)"

# ── Secondary schedulers (health + 5xx watcher) ───────────────────────
# Recreate idempotently (delete+create, since update doesn't support changing auth mode).
create_internal_scheduler() {
  local job="$1" sched="$2" path="$3" deadline="$4"
  if /opt/homebrew/bin/gcloud scheduler jobs describe "$job" --location="$REGION" --project="$PROJECT" &>/dev/null; then
    /opt/homebrew/bin/gcloud scheduler jobs delete "$job" --location="$REGION" --project="$PROJECT" --quiet
  fi
  /opt/homebrew/bin/gcloud scheduler jobs create http "$job" \
    --location="$REGION" \
    --schedule="$sched" \
    --uri="$SERVICE_URL$path" \
    --http-method=POST \
    --time-zone="UTC" \
    --attempt-deadline="$deadline" \
    --project="$PROJECT" \
    --oidc-service-account-email="$SCHEDULER_SA" \
    --oidc-token-audience="$SERVICE_URL" >/dev/null
}

# Hourly health digest (DMs on problems). Was created manually — codified here 2026-08-02.
create_internal_scheduler "mergecash-health"    "0 * * * *"  "/api/internal/mergecash-health"    "120s"
# Near-real-time (10-min) player-facing 5xx / gateway-timeout watcher (added 2026-08-02).
create_internal_scheduler "mergecash-5xx-watch" "*/10 * * * *" "/api/internal/mergecash-5xx-watch" "60s"

echo ""
echo "Schedulers: verify-progress (4h), health (1h), 5xx-watch (10m)"
echo "Access via VPN: $GATEWAY_URL"
