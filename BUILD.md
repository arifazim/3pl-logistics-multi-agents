# Build Instructions - Capstone Vertical Slice

Complete guide to build the **3PL Orchestrator** — a production-grade autonomous logistics system.

## Capstone Scope

This is a **real autonomous system**, not a demo. It implements:

- **1 Real ADK Agent**: `QuotationDecisionAgent` with Gemini LLM orchestration
- **1 Real MCP Server**: `mcp_servers/pl3_server` — stdio JSON-RPC protocol
- **3 Deterministic Tools**: `QuotationEngine`, `VendorScorer`, `MarginEvaluator`
- **3 Autonomous Loops**: Vendor evaluator, compliance-critic, kaizen meta-loop
- **A2A Protocol**: Vendor negotiation via `vendor_negotiation`
- **HITL Gate**: Deterministic escalation for exceptions

## Prerequisites

1. **Python 3.11+** installed
2. **uv** package manager installed
3. **GEMINI_API_KEY** environment variable set (for live ADK agent)
4. **google-adk** package installed

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Set Gemini API key (required for live ADK; tests use ALLOW_OFFLINE_AGENT=1)
export GEMINI_API_KEY="your-api-key"
```

## Step 1: Install Dependencies

```bash
# Sync project dependencies
uv sync
```

## Step 2: MCP Server (Real stdio Protocol)

The MCP server is already implemented at `mcp_servers/pl3_server/server.py`.

**Namespaces:**

- `rate_card` — Customer lane metadata, vendor rates
- `vendor` — Vendor directory, reliability scoring, ranking
- `policy` — Gherkin-backed policies with comparator operators
- `telemetry` — Operational KPIs, event logging
- `tms` — Shipment management

**Run MCP server:**

```bash
PYTHONPATH=. python -m mcp_servers.pl3_server.server
```

## Step 3: ADK Agent

The ADK agent is already implemented at `runtime/agents/quotation_decision_agent.py`.

**Features:**

- Loads `.agy` file + skills
- Runs `InMemoryRunner` with Gemini when `GEMINI_API_KEY` is set
- Tools: `rank_vendors_for_lane`, `compute_margin_quote`, `check_compliance`, `sanitize_vendor_text`
- Offline mode for tests (`ALLOW_OFFLINE_AGENT=1`)

## Step 4: Deterministic Tools

**QuotationEngine** (`runtime/tools/quotation_engine.py`):

- Margin from selected vendor effective cost
- 12% margin floor enforced deterministically
- SLA premiums, weight surcharges

**VendorScorer** (`runtime/tools/vendor_scorer.py`):

- 70% reliability / 30% cost weighting
- Calls MCP `vendor.rank_for_lane`

**MarginEvaluator** (`runtime/evaluation/evaluator.py`):

- Deterministic margin calculation
- Competitiveness band check
- Reliability threshold check

## Step 5: Autonomous Loops

**Loop 1: Vendor Evaluator-Optimizer** (`runtime/loops/loop1_vendor_evaluator.py`):

- Max 5 iterations
- Shrinking candidate set
- Deterministic margin check
- HITL escalation

**Loop 2: Compliance-Critic → Replan** (`runtime/loops/loop2_compliance_replan.py`):

- Max 3 iterations
- A2A handoff
- Deterministic compliance checks
- Bounded replan

**Loop 3: Kaizen Meta-Loop** (`runtime/loops/loop3_kaizen.py`):

- Max 3 iterations
- pytest eval
- Kaizen log population
- Spec refinement

## Step 6: Frontend Dashboard

FastAPI app at `frontend/cloudrun_app/app.py` with:

- `GET /health` — Agent metadata
- `GET /api/telemetry` — KPIs via MCP
- `POST /api/dual-quote` — Dual quotation workflow
- `GET /` — Dashboard UI

**Run dashboard:**

```bash
python frontend/cloudrun_app/app.py
```

Access at `http://localhost:9000`

## Step 7: Tests

```bash
# Unit tests (offline agent orchestration)
ALLOW_OFFLINE_AGENT=1 PYTHONPATH=. pytest tests/unit/ -v

# Trajectory tests
ALLOW_OFFLINE_AGENT=1 PYTHONPATH=. pytest tests/trajectory/ -v

# Loop tests (bounded iteration verification)
ALLOW_OFFLINE_AGENT=1 PYTHONPATH=. pytest tests/unit/test_loop*.py -v
```

## Step 8: Run Full System

```bash
# Terminal 1: MCP server (stdio)
PYTHONPATH=. python -m mcp_servers.pl3_server.server

# Terminal 2: Dashboard API
python frontend/cloudrun_app/app.py
```

## Demo with Live LLM

```bash
export GEMINI_API_KEY="..."
curl -X POST http://localhost:9000/api/dual-quote \
  -H 'Content-Type: application/json' \
  -d '{"lane":"Tracy->Fremont","weight":1000,"delivery_time":20}'
```

## Architecture Summary

| Component        | File                                         | Real-World Alignment                            |
| ---------------- | -------------------------------------------- | ----------------------------------------------- |
| MCP Server       | `mcp_servers/pl3_server/server.py`           | stdio JSON-RPC, production protocol             |
| ADK Agent        | `runtime/agents/quotation_decision_agent.py` | Real tool orchestration with Gemini             |
| Quotation Engine | `runtime/tools/quotation_engine.py`          | Deterministic margin from selected vendor cost  |
| Vendor Scorer    | `runtime/tools/vendor_scorer.py`             | 70/30 reliability/cost weighting via MCP        |
| Margin Evaluator | `runtime/evaluation/evaluator.py`            | Deterministic checks for loops                  |
| Loop 1           | `runtime/loops/loop1_vendor_evaluator.py`    | Bounded vendor selection with margin guardrails |
| Loop 2           | `runtime/loops/loop2_compliance_replan.py`   | A2A compliance-critic with bounded replan       |
| Loop 3           | `runtime/loops/loop3_kaizen.py`              | Kaizen meta-loop with pytest eval               |
| HITL Gate        | `runtime/hitl/gate.py`                       | Deterministic escalation, not an agent          |
| Frontend         | `frontend/cloudrun_app/app.py`               | FastAPI with dual-quote endpoint                |

## What This Is NOT

- **NOT a demo** — Production-grade code with real MCP protocol
- **NOT a tautology** — Margin computed from selected vendor cost
- **NOT LLM math** — All financial calculations deterministic
- **NOT unbounded loops** — All loops have max iterations and escalation

## What's Built

All components listed in this guide are fully implemented. See `ARCHITECTURE.md` for the
complete system design and `REVIEW.md` for a capability-by-capability breakdown.

---

## Google Cloud Deployment

Deploy the Zero-Touch 3PL Orchestrator to Google Cloud Run.

### Prerequisites

1. **Google Cloud SDK** installed and authenticated
2. **Google Cloud project** created
3. **Artifact Registry** enabled
4. **Cloud Run API** enabled

```bash
# Install Google Cloud SDK
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
gcloud init

# Enable required APIs
gcloud services enable artifactregistry.googleapis.com
gcloud services enable run.googleapis.com
```

### Step 1: Create Dockerfile

Create `deployment/cloudrun/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen

# Copy application code
COPY runtime/ ./runtime/
COPY agy/ ./agy/
COPY mcp_servers/ ./mcp_servers/
COPY frontend/cloudrun_app/ ./frontend/cloudrun_app/

# Expose port
EXPOSE 9000

# Run application
CMD ["uv", "run", "python", "frontend/cloudrun_app/app.py"]
```

### Step 2: Build and Push Docker Image

```bash
# Set project variables
export PROJECT_ID="your-project-id"
export REGION="us-central1"
export IMAGE_NAME="3pl-orchestrator"
export IMAGE_URI="us-central1-docker.pkg.dev/${PROJECT_ID}/${IMAGE_NAME}/${IMAGE_NAME}"

# Build Docker image
docker build -t ${IMAGE_URI} -f deployment/cloudrun/Dockerfile .

# Configure Docker authentication
gcloud auth configure-docker ${REGION}-docker.pkg.dev

# Push image
docker push ${IMAGE_URI}
```

### Step 3: Create Secret for GEMINI_API_KEY

```bash
# Create secret in Secret Manager
echo "your-gemini-api-key" | gcloud secrets create gemini-api-key --data-file=-

# Grant Cloud Run service account access to secret
gcloud secrets add-iam-policy-binding gemini-api-key \
  --member="serviceAccount:$(gcloud iam service-accounts list --filter='displayName:Cloud Run Service Agent' --format='value(email)')" \
  --role="roles/secretmanager.secretAccessor"
```

### Step 4: Deploy to Cloud Run

```bash
# Deploy service
gcloud run deploy 3pl-orchestrator \
  --image=${IMAGE_URI} \
  --platform=managed \
  --region=${REGION} \
  --allow-unauthenticated \
  --port=9000 \
  --set-secrets=GEMINI_API_KEY=gemini-api-key:latest \
  --cpu=2 \
  --memory=2Gi \
  --max-instances=10 \
  --min-instances=1
```

### Step 5: Verify Deployment

```bash
# Get service URL
gcloud run services describe 3pl-orchestrator \
  --platform=managed \
  --region=${REGION} \
  --format='value(status.url)'

# Test health endpoint
curl https://YOUR_SERVICE_URL/health

# Test dual-quote endpoint
curl -X POST https://YOUR_SERVICE_URL/api/dual-quote \
  -H 'Content-Type: application/json' \
  -d '{"lane":"Tracy->Fremont","weight":1000,"delivery_time":20}'
```

### Step 6: Monitor and Logs

```bash
# View logs
gcloud run logs tail 3pl-orchestrator --platform=managed --region=${REGION}

# View metrics
gcloud run services describe 3pl-orchestrator --platform=managed --region=${REGION}
```

### Cloud Run Service YAML

Create `deployment/cloudrun/service.yaml` for declarative deployment:

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: 3pl-orchestrator
spec:
  template:
    spec:
      containers:
        - image: us-central1-docker.pkg.dev/PROJECT_ID/3pl-orchestrator/3pl-orchestrator
          ports:
            - containerPort: 9000
          env:
            - name: GEMINI_API_KEY
              valueFrom:
                secretKeyRef:
                  name: gemini-api-key
                  key: latest
          resources:
            limits:
              cpu: "2"
              memory: "2Gi"
      containerConcurrency: 10
      timeoutSeconds: 300
```

Deploy with YAML:

```bash
gcloud run services replace deployment/cloudrun/service.yaml
```

### Cost Optimization

- **Min instances**: 1 (always warm for quick response)
- **Max instances**: 10 (scale up during peak)
- **CPU**: 2 vCPU (sufficient for ADK agent + MCP tools)
- **Memory**: 2Gi (enough for Python runtime + LLM context)

Estimated cost: ~$50-100/month for moderate traffic.

### Security Best Practices

1. **Secret Management**: Use Secret Manager for API keys
2. **IAM**: Grant least privilege to service account
3. **VPC**: Consider VPC connector for private MCP servers
4. **Authentication**: Remove `--allow-unauthenticated` for production
5. **HTTPS**: Cloud Run provides automatic HTTPS

### Troubleshooting

**Build fails:**

```bash
# Check Docker build logs
docker build -t ${IMAGE_URI} -f deployment/cloudrun/Dockerfile . --no-cache
```

**Deployment fails:**

```bash
# Check Cloud Run logs
gcloud run logs tail 3pl-orchestrator --platform=managed --region=${REGION}
```

**Secret not accessible:**

```bash
# Verify IAM policy
gcloud secrets get-iam-policy gemini-api-key
```

**Service not responding:**

```bash
# Check service status
gcloud run services describe 3pl-orchestrator --platform=managed --region=${REGION}
```
