Deployment instructions

Recommended quick steps to deploy the BYOV Streamlit app with Workflow API.

## Overview

This repository contains two applications:
1. **Streamlit App** (`byov_app.py`) - User-facing enrollment wizard
2. **Workflow API** (`workflow-api/`) - Node.js backend for admin approval workflow

Both can be deployed together or separately depending on your platform.

---

## Option 1: Streamlit Community Cloud

**Best for:** Simple Streamlit-only deployment (Workflow API must be hosted separately)

### Steps:
- Push this repository to GitHub.
- Add the repo to Streamlit Community Cloud (https://streamlit.io/cloud).
- Add sensitive values in the Streamlit "Secrets" section (see `secrets.toml` example below).
- The app entry point is `byov_app.py`; Streamlit will run it with `streamlit run byov_app.py`.
- **For Workflow API:** Deploy separately on Render, Railway, or Heroku (see Option 3 below).

---

## Option 2: Heroku (Both Apps Together)

**Best for:** Single platform deployment with both apps

### Procfile Setup:
Create or update `Procfile` with both processes:

```
web: streamlit run byov_app.py --server.port $PORT --server.address 0.0.0.0
worker: cd workflow-api && npm install && npm start
```

### Buildpacks:
Add both Python and Node.js buildpacks:
```bash
heroku buildpacks:add heroku/python
heroku buildpacks:add heroku/nodejs
```

### Environment Variables:
Set in Heroku Config Vars:
```
# Streamlit Config
SENDGRID_API_KEY=SG.xxxxxx
SENDGRID_FROM_EMAIL=byov@yourdomain.com

# Workflow API Config
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/byov
WORKFLOW_INTERNAL_TOKEN=your-shared-secret-token
BYOV_DASHBOARD_API_URL=https://your-dashboard.herokuapp.com
PORT=3000
```

### Deploy:
```bash
git push heroku main
```

---

## Option 3: Render (Recommended for Production)

**Best for:** Scalable production deployment with free tier available

### Deploy Streamlit App:
1. Create a new **Web Service** on Render
2. Connect your GitHub repo
3. Configure:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `streamlit run byov_app.py --server.port $PORT --server.address 0.0.0.0`
   - **Environment:** Python 3
4. Add environment variables in Render dashboard

### Deploy Workflow API:
1. Create another **Web Service** on Render
2. Connect same GitHub repo
3. Configure:
   - **Root Directory:** `workflow-api`
   - **Build Command:** `npm install && npm run build`
   - **Start Command:** `npm start`
   - **Environment:** Node
4. Add MongoDB URI and other env variables
5. Note the API URL for Streamlit app integration

---

## Option 4: Railway

**Best for:** Easy deployment with automatic detection

### Steps:
1. Connect your GitHub repo to Railway
2. Railway auto-detects both Python and Node.js
3. Configure environment variables:
   - For Streamlit app: Set `PYTHONPATH` and email configs
   - For Workflow API: Set MongoDB, SendGrid, and token configs
4. Set start commands if needed:
   - Streamlit: `streamlit run byov_app.py --server.port $PORT`
   - Workflow API: `cd workflow-api && npm start`

---

## Option 5: Docker Deployment

**Best for:** Custom hosting or VPS deployment

### Dockerfile (Streamlit):
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "byov_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

### Dockerfile (Workflow API):
```dockerfile
FROM node:18-alpine
WORKDIR /app/workflow-api
COPY workflow-api/package*.json ./
RUN npm install
COPY workflow-api/ .
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
```

### Docker Compose:
```yaml
version: '3.8'
services:
  streamlit:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8501:8501"
    environment:
      - DASHBOARD_API_URL=http://workflow-api:3000
    
  workflow-api:
    build:
      context: .
      dockerfile: workflow-api/Dockerfile
    ports:
      - "3000:3000"
    environment:
      - MONGODB_URI=mongodb://mongo:27017/byov
      - PORT=3000
    
  mongo:
    image: mongo:6
    ports:
      - "27017:27017"
    volumes:
      - mongo-data:/data/db

volumes:
  mongo-data:
```

Deploy with:
```bash
docker-compose up -d
```

---

## Secrets and Credentials

2) Heroku (or other PaaS)
- Make sure `requirements.txt` is up-to-date.
- Include a `Procfile` with the following content:

  web: streamlit run byov_app.py --server.port $PORT --server.address 0.0.0.0

- Push to Heroku; the Procfile will instruct the dyno to run Streamlit.

Secrets and credentials
- Do NOT commit real credentials into the repository. Use platform secret managers (Streamlit secrets, Heroku config vars, GitHub Actions secrets, etc.).
- Example `secrets.toml` (DO NOT COMMIT real values):

  [email]
  sender = "you@example.com"
  app_password = "your-app-password"
  recipient = "recipient@example.com"

## Files and Artifacts

- Uploaded files and generated PDFs are stored in `uploads/` and `pdfs/`.
- Workflow API logs and data stored in `workflow-api/logs/` and `workflow-api/data/`.
- These directories are gitignored to avoid committing user data.

---

## Local Development

### Run Streamlit App:
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows (or source .venv/bin/activate on Linux/Mac)
pip install -r requirements.txt
streamlit run byov_app.py
```

### Run Workflow API:
```bash
cd workflow-api
npm install
copy .env.example .env  # Edit with your config
npm start
```

### Run Both Together (Development):
**Terminal 1:**
```bash
streamlit run byov_app.py
```

**Terminal 2:**
```bash
cd workflow-api && npm run dev
```

---

## MongoDB Setup

### Local MongoDB:
```bash
# Install MongoDB Community Edition
# Start service
mongod --dbpath C:\data\db
```

### Cloud MongoDB (Atlas - Recommended):
1. Create free cluster at https://www.mongodb.com/cloud/atlas
2. Create database user
3. Whitelist IP (0.0.0.0/0 for development)
4. Get connection string: `mongodb+srv://username:password@cluster.mongodb.net/byov`
5. Set as `MONGODB_URI` environment variable

---

## Integration Testing

Test the full workflow locally:

```bash
# Terminal 1: Start MongoDB (if local)
mongod --dbpath C:\data\db

# Terminal 2: Start Workflow API
cd workflow-api
npm start

# Terminal 3: Start Streamlit
streamlit run byov_app.py

# Terminal 4: Run workflow test
cd workflow-api
npm run workflow:test
```

---

## Troubleshooting

### Workflow API won't start:
- Check MongoDB connection string
- Verify Node.js version (>= 14)
- Run `npm install` in workflow-api directory
- Check logs in `workflow-api/logs/`

### Streamlit app can't connect to API:
- Verify `DASHBOARD_API_URL` environment variable
- Check workflow API is running and accessible
- Verify `WORKFLOW_INTERNAL_TOKEN` matches on both apps

### Emails not sending:
- Check SendGrid API key is valid
- Verify sender email is authenticated with SendGrid
- Check SMTP credentials if using fallback
- Review logs for email errors

### Database connection issues:
- Verify MongoDB URI format
- Check network access (Atlas IP whitelist)
- Ensure database user has correct permissions

---

## Production Checklist

- [ ] Set strong `WORKFLOW_INTERNAL_TOKEN`
- [ ] Use MongoDB Atlas or managed database
- [ ] Configure SendGrid for email delivery
- [ ] Set up SSL/HTTPS for both apps
- [ ] Configure CORS if apps on different domains
- [ ] Enable database backups
- [ ] Set up monitoring and logging
- [ ] Review `.gitignore` - no secrets committed
- [ ] Test workflow end-to-end
- [ ] Document API URL for team

---

_Last updated: November 2025 - Added Workflow API deployment instructions_
