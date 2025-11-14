## Tuki Backend on Google Cloud Run — Platform Context and Canonical Deploy

This document captures how the backend runs in production on Google Cloud Run so that any external agent can reason about the system, reproduce deploys, and troubleshoot reliably.

### Service Overview
- Service name: `tuki-backend`
- Region: `us-central1`
- Image registry: `us-central1-docker.pkg.dev/tukiprod/tuki-repo`
- Runtime: Python 3.11 + Django 4.2 + Gunicorn
- Entrypoint (web): Gunicorn binding to `:$PORT` (Cloud Run injects `PORT`)
- Health endpoint: `GET /healthz` (no DB/Redis access)

### Networking
- Cloud SQL (PostgreSQL) via Unix socket path in `DB_HOST`:
  - Example: `/cloudsql/tukiprod:us-central1:tuki-db-prod`
- Serverless VPC Access Connector: `serverless-conn`
- VPC egress: `private-ranges-only` (critical). Private traffic (Cloud SQL) goes through the connector; Google APIs go over public egress.

### Scaling & Capacity
- min instances: 1
- max instances: 100 (quota-compliant)
- concurrency: 200 requests/instance
- resources: 1 vCPU, 1 GiB RAM, request timeout 300s

### Canonical Artifacts (keep these)
- Web image Dockerfile: `backtuki/Dockerfile.backend`
- Cloud Build (web): `backtuki/cloudbuild-backend.yaml` → tags image `tuki-backend:v4-backend`
- Cloud Build (migrate helper image): `backtuki/cloudbuild-migrate.yaml` → tags image `tuki-migrate:latest`
- Cloud Run env vars file: `backtuki/cloud-run-env.yaml`

Legacy/alternative Dockerfiles may exist (`Dockerfile`, `Dockerfile.cloudrun`, `Dockerfile.hybrid`, Celery images). Treat them as non-canonical unless explicitly referenced in a task.

### Environment Variables (required/expected)
Provided via `cloud-run-env.yaml`, loaded at service deploy and at jobs runtime.

Required for DB:
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` (5432)

Secrets & Security:
- `SECRET_KEY`
- `ALLOWED_HOSTS` (includes `*.run.app`, production domains)
- `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS`

Static/Media storage:
- `USE_GCP`: "true" enables GCS storage branches in settings
- `GS_PROJECT_ID`, `GS_BUCKET_NAME` (required when `USE_GCP=true`)

Cache & Sessions (Redis optional):
- `USE_REDIS`: "false" by default on Cloud Run
- If enabling Redis: `REDIS_URL` (e.g., Memorystore private IP). With `USE_REDIS=false`, settings fall back to DB cache and DB sessions (production has this logic).

Other helpful vars:
- `DJANGO_SETTINGS_MODULE`: `config.settings.cloudrun`
- `FRONTEND_URL` (optional), `TRANSBANK_WEBPAY_PLUS_SANDBOX` (optional)

### Admin Login Model
- The login form uses email as the identifier. Use the superuser email when signing in.

### Canonical Deploy Flow
1) Build web image
```
cd backtuki
gcloud builds submit --config cloudbuild-backend.yaml
```

2) Deploy service (note: VPC egress private-ranges-only)
```
gcloud run deploy tuki-backend \
  --image us-central1-docker.pkg.dev/tukiprod/tuki-repo/tuki-backend:v4-backend \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --min-instances 1 \
  --max-instances 100 \
  --concurrency 200 \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --env-vars-file cloud-run-env.yaml \
  --vpc-connector serverless-conn \
  --vpc-egress private-ranges-only \
  --service-account 187635794409-compute@developer.gserviceaccount.com
```

3) Run DB migrations (Cloud Run Job)
Option A (use migrate image built by `cloudbuild-migrate.yaml`):
```
gcloud run jobs deploy tuki-migrate \
  --image us-central1-docker.pkg.dev/tukiprod/tuki-repo/tuki-migrate:latest \
  --region us-central1 \
  --env-vars-file backtuki/cloud-run-env.yaml \
  --vpc-connector serverless-conn \
  --vpc-egress private-ranges-only \
  --service-account 187635794409-compute@developer.gserviceaccount.com \
  --execute-now --wait \
  --command python,manage.py,migrate
```

Option B (reuse web image briefly):
```
gcloud run jobs deploy tuki-migrate \
  --image us-central1-docker.pkg.dev/tukiprod/tuki-repo/tuki-backend:v4-backend \
  --region us-central1 \
  --env-vars-file backtuki/cloud-run-env.yaml \
  --vpc-connector serverless-conn \
  --vpc-egress private-ranges-only \
  --service-account 187635794409-compute@developer.gserviceaccount.com \
  --execute-now --wait \
  --command python,manage.py,migrate
```

4) Create superuser (non-interactive)
The project provides `backtuki/apps/users/management/commands/create_initial_superuser.py` using Django's standard env vars.
```
gcloud run jobs deploy tuki-create-su \
  --image us-central1-docker.pkg.dev/tukiprod/tuki-repo/tuki-backend:v4-backend \
  --region us-central1 \
  --env-vars-file backtuki/cloud-run-env.yaml \
  --set-env-vars DJANGO_SUPERUSER_USERNAME=admin,DJANGO_SUPERUSER_EMAIL=admin@tuki.cl,DJANGO_SUPERUSER_PASSWORD='TukiAdmin2025!' \
  --vpc-connector serverless-conn \
  --vpc-egress private-ranges-only \
  --service-account 187635794409-compute@developer.gserviceaccount.com \
  --execute-now --wait \
  --command python,manage.py,create_initial_superuser
```

5) Verify
- Health: `curl -I https://<service-url>/healthz` → 200
- Admin loads: `GET /admin/` → 302 to `/admin/login/` then 200
- Public API: `GET /api/v1/events/public_list/` → 200 JSON

### Troubleshooting Notes
- If requests hang or the DB connection times out, verify VPC egress is `private-ranges-only` and the connector exists and is authorized; confirm Cloud SQL IAM roles on the service account (`cloudsql.client`, `cloudsql.instanceUser`).
- If admin returns 500 with missing static assets (e.g., `Missing staticfiles manifest entry`), ensure `collectstatic` runs at startup (current web image does this) and that `STATICFILES_STORAGE` is set; Cloud Run instances are ephemeral but persistent across requests.
- If Redis is not reachable, set `USE_REDIS=false` to fall back to DB cache/sessions (already implemented in production settings).
- Superuser login uses email. Use the email in the form, not the username.

### Non-canonical / legacy items
- Multiple Dockerfiles exist from prior iterations. Unless your task is about Celery or specific experiments, avoid them. The canonical web entrypoint is `Dockerfile.backend` + this document.

---
This document is the authoritative context for deploying and diagnosing the backend on Cloud Run.

