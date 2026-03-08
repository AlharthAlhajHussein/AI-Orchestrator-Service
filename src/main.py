from fastapi import FastAPI 
from routers.pubsub import pubsub_router
from routers.base import base_router


# --- 2. Initialize App and Clients ---
app = FastAPI(title="AI Orchestrator Service", 
              version="0.1.0", 
              description="API for orchestrating AI agents across multiple platforms", 
              contact={"name": "AI Orchestrator Team", "email": "alharth.alhaj.hussein@gmail.com"}, 
              openapi_url="/openapi.json", 
              docs_url="/docs", 
              redoc_url="/redoc")

app.include_router(base_router)
app.include_router(pubsub_router)
