# BYOV Workflow API

Node.js/TypeScript API server for managing technician enrollment workflow and approval processes.

## Features

- **Admin Review System**: Approve/reject enrollment requests
- **Workflow Orchestration**: Manages enrollment lifecycle (submission → review → approval)
- **Dashboard Integration**: Creates technician records in BYOVDashboard after approval
- **Email Notifications**: SendGrid and SMTP support for approval emails
- **RESTful API**: Express-based endpoints for technicians and admins

## Prerequisites

- Node.js 14+ and npm 6+
- MongoDB instance (local or cloud)
- SendGrid API key (optional, falls back to SMTP)

## Setup

1. **Install dependencies:**
   ```bash
   cd workflow-api
   npm install
   ```

2. **Configure environment:**
   ```bash
   copy .env.example .env
   ```
   Edit `.env` with your configuration:
   - MongoDB connection string
   - SendGrid API key or SMTP credentials
   - Dashboard API URL and token
   - Port number (default: 3000)

3. **Build TypeScript:**
   ```bash
   npm run build
   ```

4. **Start the server:**
   ```bash
   npm start
   ```
   
   For development with auto-reload:
   ```bash
   npm run dev
   ```

## API Endpoints

### Technician Routes (`/api/technicians`)
- `POST /api/technicians` - Submit new enrollment
- `GET /api/technicians/:id` - Get enrollment by ID
- `GET /api/technicians?techId=<id>` - Check if technician exists

### Admin Routes (`/api/admin`)
- `POST /api/admin/approve/:id` - Approve enrollment
- `POST /api/admin/reject/:id` - Reject enrollment
- `GET /api/admin/enrollments` - List all pending enrollments

**Note:** Admin routes require `X-Internal-Token` header for authentication.

## Deployment

### Deploy with Streamlit Cloud

The workflow API can run alongside your Streamlit app. See `DEPLOYMENT.md` for platform-specific instructions:

- **Render**: Deploy as a Web Service
- **Railway**: Auto-detected Node.js app
- **Heroku**: Uses `Procfile` for both apps
- **Streamlit Cloud**: Run API in background with `setup.sh`

### Environment Variables (Production)

Set these in your deployment platform:
```
PORT=3000
MONGODB_URI=<your-mongodb-atlas-uri>
BYOV_DASHBOARD_API_URL=<your-dashboard-url>
WORKFLOW_INTERNAL_TOKEN=<shared-secret-token>
SENDGRID_API_KEY=<sendgrid-key>
SENDGRID_FROM_EMAIL=<sender-email>
```

## Testing

Run workflow test:
```bash
npm run workflow:test
```

Safe mode (no external calls):
```bash
set EMAIL_DISABLED=true
set DASHBOARD_DISABLED=true
npm run workflow:test
```

## Integration with Streamlit App

The Python Streamlit app and Node.js workflow API work together:

1. **Streamlit App** (`byov_app.py`) - Collects technician submissions
2. **Workflow API** - Handles admin approval process
3. **Both sync** via BYOVDashboard API using shared token

## License

MIT License
