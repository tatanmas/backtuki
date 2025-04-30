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