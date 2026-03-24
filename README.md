# AI-Orchestrator-Service

Welcome to the central "brain" of the Agents Platform. This service connects user inputs to AI models, orchestrates RAG retrievals, processes media, and handles message dispatching.

For a deep dive into the architecture, edge cases, and tech stack, please read the [SERVICE_DOCUMENTATION.md](./SERVICE_DOCUMENTATION.md).

---

## Prerequisites
- **Python 3.13** (via Conda recommended)
- **Docker & Docker Compose** (for Redis and PostgreSQL)
- **UV** package manager
- **API Keys**: Google Gemini API Key & GCP Service Account credentials (for Pub/Sub & Cloud Storage)

---

## Setup & Installation (Manual Development Mode)

### 1. Set up Environment Configuration
Create a `.env` file in the root directory you can copy from `.env.example` and configure your database, Redis, GCP, and Gemini credentials.
```bash
cp .env.example .env
```

### 2. Create and Activate Conda Environment
```bash
conda create -n ai-orchestrator-env python=3.13 uv -c conda-forge
conda activate ai-orchestrator-env
```

### 3. Install Dependencies
```bash
cd src
uv pip install -r requirements.txt
```

### 4. Start Infrastructure (Database & Redis)
Create your own `docker-compose.yml` file for backing services (Redis, PostgreSQL):
```bash
docker-compose up -d postgres_ai redis
```

### 5. Start the FastAPI App
Make sure you run the app from inside the `src` directory so imports work correctly.
```bash
cd src
uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

---

## Database Migrations (Alembic)

Before running the app for the first time, you must initialize the database schema.

### 1. Go to the DB folder
```bash
cd src/models/db
```

### 2. Init Alembic (if not already initialized)
```bash
alembic init -t async migrations
```

### 3. Generate a new migration revision
```bash
alembic revision --autogenerate -m "Initial schema"
```

### 4. Apply changes to DB
```bash
alembic upgrade head
```
