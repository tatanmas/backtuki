# Tuki Backend

## Setup

### Google Cloud Credentials

1. Copy the example credentials file:
```bash
cp gcp-credentials.json.example gcp-credentials.json
```

2. Replace the placeholder values in `gcp-credentials.json` with your actual Google Cloud service account credentials.

**Important:** Never commit the actual `gcp-credentials.json` file to Git. It's already in `.gitignore`.

## Cloud Run Deployment (Backend)

Canonical docs: see `deploy/CONTEXT_CLOUD_RUN.md` for platform context and the authoritative deploy flow.

1) Build and push the web image

```bash
gcloud builds submit --config cloudbuild-backend.yaml
```

2) Deploy to Cloud Run (ensure Cloud SQL and VPC connector)

```bash
gcloud run deploy tuki-backend \
  --image us-central1-docker.pkg.dev/tukiprod/tuki-repo/tuki-backend:v4-backend \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --max-instances 10 \
  --concurrency 80 \
  --memory 1Gi \
  --cpu 2 \
  --env-vars-file cloud-run-env.yaml \
  --vpc-connector serverless-conn \
  --vpc-egress private-ranges-only
```

3) Run migrations via Cloud Run Job

```bash
./scripts/deploy-migrations.sh
```

4) Create initial superuser (one-time)

```bash
gcloud run jobs create tuki-create-su \
  --image us-central1-docker.pkg.dev/tukiprod/tuki-repo/tuki-migrate:latest \
  --region us-central1 \
  --env-vars-file migrate-env.yaml \
  --set-env-vars DJANGO_SUPERUSER_USERNAME=admin,DJANGO_SUPERUSER_EMAIL=admin@tuki.cl,DJANGO_SUPERUSER_PASSWORD='TukiAdmin2025!' \
  --set-cloudsql-instances tukiprod:us-central1:tuki-db-prod \
  -- \
  python manage.py create_initial_superuser

gcloud run jobs execute tuki-create-su --region us-central1 --wait
```

Alternative using Django's built-in command:
```bash
gcloud run jobs create tuki-create-su-native \
  --image us-central1-docker.pkg.dev/tukiprod/tuki-repo/tuki-migrate:latest \
  --region us-central1 \
  --env-vars-file migrate-env.yaml \
  --set-env-vars DJANGO_SUPERUSER_USERNAME=admin,DJANGO_SUPERUSER_EMAIL=admin@tuki.cl,DJANGO_SUPERUSER_PASSWORD='TukiAdmin2025!' \
  --set-cloudsql-instances tukiprod:us-central1:tuki-db-prod \
  -- \
  python manage.py createsuperuser --noinput

gcloud run jobs execute tuki-create-su-native --region us-central1 --wait
```

5) Health check

Endpoint: `/healthz` must return `200 ok`.

# Tuki Platform Backend

Tuki is a comprehensive platform for selling tickets, managing accommodations, and offering experiences, with a focus on multi-tenancy and scalability.

## Features

- **Multi-tenant architecture**: Separate organizations with their own data
- **Event management**: Create, manage and sell tickets for events
- **Accommodation management**: Integrate with Airbnb, Booking.com and others
- **Experience management**: Create and sell unique experiences
- **E-commerce**: Payment processing, invoicing, ticket generation
- **API-first design**: Well-documented REST API for frontend integration
- **Offline/online ticket validation**: Mobile app integration

## Technology Stack

- **Framework**: Django 4.2 + Django REST Framework
- **Database**: PostgreSQL (production) / SQLite (development)
- **Caching**: Redis
- **Task Queue**: Celery
- **API Documentation**: drf-spectacular (OpenAPI 3.0, Swagger, ReDoc)
- **Containerization**: Docker & Docker Compose
- **Authentication**: JWT tokens
- **Storage**: Local storage (dev) / AWS S3 (production)
- **CI/CD**: GitHub Actions (optional)

## Development Setup

### Prerequisites

- Docker and Docker Compose
- Git

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/tuki-platform.git
cd tuki-platform/backtuki
```

2. Create an environment file:
```bash
cp .env-example .env
```

3. Edit the `.env` file with your configuration

4. Build and start the development environment:
```bash
docker-compose up -d
```

5. Run migrations:
```bash
docker-compose exec web python manage.py migrate
```

6. Create a superuser:
```bash
docker-compose exec web python manage.py createsuperuser
```

7. Access the API at http://localhost:8000/api/v1/
8. Access the API documentation at http://localhost:8000/api/docs/

## Project Structure

The project follows a modular structure:

- `config/`: Django project configuration
- `apps/`: Main application modules
  - `users/`: User authentication and profiles
  - `organizers/`: Multi-tenant organizer management
  - `events/`: Event and ticket management
  - `accommodations/`: Accommodation management and channel integration
  - `experiences/`: Experience management
  - `reservations/`: Booking and reservation system
  - `payments/`: Payment processing and invoicing
  - `ticket_validation/`: Ticket validation system
- `api/`: API endpoints
  - `v1/`: Version 1 API
- `core/`: Shared functionality
- `services/`: External service integrations
- `tasks/`: Celery tasks

## API Documentation

The API is documented using OpenAPI 3.0 and can be viewed through:

- Swagger UI: `/api/docs/`
- ReDoc: `/api/redoc/`
- OpenAPI Schema: `/api/schema/`

## Testing

Run the test suite with:

```bash
docker-compose exec web python manage.py test
```

## Deployment

For production deployment, see the [deployment guide](docs/deployment.md).

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct, and the process for submitting pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details. 