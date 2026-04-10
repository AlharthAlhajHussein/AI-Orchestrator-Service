from fastapi import Request, HTTPException, status
from helpers.config import settings
from google.oauth2 import id_token
from google.auth.transport import requests
import logging

logger = logging.getLogger("uvicorn.error")

async def verify_internal_secret(request: Request):
    """
    Validates incoming requests. Supports two methods:
    1. X-Internal-Secret: Used for local testing and internal microservice calls.
    2. Google OIDC Token: Used by GCP Pub/Sub Push in production.
    """
    # --- Method 1: Local / Internal Secret Check ---
    internal_secret = request.headers.get("X-Internal-Secret")
    if internal_secret and internal_secret == settings.internal_secret_between_services:
        return {"email": "local-developer-bypass"}

    # --- Method 2: GCP Pub/Sub OIDC Token Check ---
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("Blocked access attempt: Missing or invalid token.")
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    token = auth_header.split(" ")[1]
    
    try:
        # Verifies the token against Google's public keys. Fails if Audience doesn't match!
        claim = id_token.verify_oauth2_token(token, requests.Request(), audience=settings.pubsub_audience)
        
        # Verify it's coming from your specific service account
        if claim.get("email") != settings.pubsub_invoker_email:
             logger.error(f"Unauthorized service account attempt: {claim.get('email')}")
             raise ValueError("Wrong service account")
             
        return claim
    except Exception as e:
        logger.error(f"GCP Token validation failed: {e}")
        raise HTTPException(status_code=403, detail="Invalid token")