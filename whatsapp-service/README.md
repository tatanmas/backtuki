# WhatsApp Service for Tuki Platform

Node.js service using `whatsapp-web.js` to connect to WhatsApp Web.

## Setup

1. Install dependencies:
```bash
npm install
```

2. Start the service:
```bash
npm start
```

3. Scan the QR code displayed in the terminal with your WhatsApp mobile app.

## Environment Variables

- `PORT`: Service port (default: 3001)
- `DJANGO_API_URL`: Django backend URL (default: http://localhost:8000)
- `SESSION_PATH`: Path to store WhatsApp sessions (default: ./sessions)

## API Endpoints

- `GET /api/status` - Get WhatsApp connection status
- `POST /api/send-message` - Send a WhatsApp message
  - Body: `{ "phone": "56912345678", "text": "Hello" }`

## Docker

Build and run with Docker:
```bash
docker-compose -f docker-compose.whatsapp.yml up -d
```

