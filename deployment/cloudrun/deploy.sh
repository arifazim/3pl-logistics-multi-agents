#!/usr/bin/env bash
# =============================================================================
# deploy.sh — One-click deploy to Google Cloud Run
#
# Usage:
#   ./deployment/cloudrun/deploy.sh [PROJECT_ID] [REGION]
#
# Examples:
#   ./deployment/cloudrun/deploy.sh my-gcp-project us-central1
#   ./deployment/cloudrun/deploy.sh                          # uses gcloud defaults
#
# Prerequisites:
#   - gcloud CLI installed and authenticated  (gcloud auth login)
#   - GEMINI_API_KEY exported in your shell, or stored in Secret Manager
# =============================================================================
set -euo pipefail

# ── Config ─────────────────────────────────────────────────────────────────
PROJECT_ID="${1:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${2:-us-central1}"
SERVICE_NAME="3pl-dashboard"
REPO_NAME="3pl-repo"
IMAGE_TAG="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:latest"
SA_NAME="3pl-dashboard-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if [[ -z "$PROJECT_ID" ]]; then
  echo "ERROR: PROJECT_ID is required. Run: gcloud config set project YOUR_PROJECT_ID"
  exit 1
fi

echo "============================================================"
echo "  3PL Quotation Intelligence — Cloud Run Deployment"
echo "  Project : $PROJECT_ID"
echo "  Region  : $REGION"
echo "  Image   : $IMAGE_TAG"
echo "============================================================"

# ── Step 1: Enable required APIs ───────────────────────────────────────────
echo ""
echo "[1/8] Enabling required GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  iam.googleapis.com \
  --project="$PROJECT_ID" --quiet

# ── Step 2: Create Artifact Registry repo (idempotent) ────────────────────
echo ""
echo "[2/8] Creating Artifact Registry repository..."
gcloud artifacts repositories describe "$REPO_NAME" \
  --project="$PROJECT_ID" --location="$REGION" &>/dev/null \
  || gcloud artifacts repositories create "$REPO_NAME" \
       --repository-format=docker \
       --location="$REGION" \
       --project="$PROJECT_ID" \
       --description="3PL dashboard images" --quiet

# ── Step 3: Service account ────────────────────────────────────────────────
echo ""
echo "[3/8] Setting up service account..."
gcloud iam service-accounts describe "$SA_EMAIL" \
  --project="$PROJECT_ID" &>/dev/null \
  || gcloud iam service-accounts create "$SA_NAME" \
       --display-name="3PL Dashboard Service Account" \
       --project="$PROJECT_ID" --quiet

# Grant Secret Manager accessor role
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor" --quiet

# ── Step 4: Store GEMINI_API_KEY in Secret Manager ─────────────────────────
echo ""
echo "[4/8] Storing GEMINI_API_KEY in Secret Manager..."
if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "  WARNING: GEMINI_API_KEY not set in environment."
  echo "  Add it manually: gcloud secrets create gemini-api-key --data-file=-"
else
  echo "$GEMINI_API_KEY" | gcloud secrets create gemini-api-key \
    --data-file=- --project="$PROJECT_ID" --replication-policy=automatic --quiet 2>/dev/null \
    || echo "$GEMINI_API_KEY" | gcloud secrets versions add gemini-api-key \
         --data-file=- --project="$PROJECT_ID" --quiet
  echo "  Secret stored/updated."
fi

# ── Step 5: Build and push Docker image ────────────────────────────────────
echo ""
echo "[5/8] Building Docker image with Cloud Build..."
# Run from project root so COPY commands in Dockerfile work
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || dirname "$0"/../..)"
gcloud builds submit . \
  --tag="$IMAGE_TAG" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --gcs-log-dir="gs://${PROJECT_ID}-cloudbuild-logs" \
  --quiet \
  || gcloud builds submit . \
       --tag="$IMAGE_TAG" \
       --project="$PROJECT_ID" \
       --quiet

# ── Step 6: Render service.yaml with real values ──────────────────────────
echo ""
echo "[6/8] Rendering service.yaml..."
RENDERED_YAML=$(mktemp /tmp/service_rendered_XXXX.yaml)
sed \
  -e "s|PROJECT_ID|${PROJECT_ID}|g" \
  -e "s|REGION|${REGION}|g" \
  deployment/cloudrun/service.yaml > "$RENDERED_YAML"

# ── Step 7: Deploy to Cloud Run ────────────────────────────────────────────
echo ""
echo "[7/8] Deploying to Cloud Run..."
gcloud run services replace "$RENDERED_YAML" \
  --region="$REGION" \
  --project="$PROJECT_ID" --quiet

# Make service publicly accessible
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --member="allUsers" \
  --role="roles/run.invoker" --quiet

rm -f "$RENDERED_YAML"

# ── Step 8: Print URL ──────────────────────────────────────────────────────
echo ""
echo "[8/8] Fetching service URL..."
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --format="value(status.url)")

echo ""
echo "============================================================"
echo "  ✓ Deployment complete!"
echo "  Dashboard : ${SERVICE_URL}"
echo "  Health    : ${SERVICE_URL}/health"
echo "  API docs  : ${SERVICE_URL}/docs"
echo "============================================================"
