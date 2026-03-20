import base64
import json
from fastapi import APIRouter, HTTPException, Response
from pydantic import ValidationError
from models.in_out_messages import IncomingMessage
from services.core_ai_logic import process_message
from routers.schems.pubsub import PubSubPushRequest
from services.pubsub_service import publish_outgoing_message
import logging 

logger = logging.getLogger("uvicorn.error")

pubsub_router = APIRouter(
    prefix="/pubsub", 
    tags=["Pub/Sub"]
)

@pubsub_router.post("/push")
async def handle_pubsub_push(request: PubSubPushRequest):
    """Receives Push messages from GCP Pub/Sub."""
    try:
        # 1. Pub/Sub sends the payload in Base64. We must decode it.
        decoded_bytes = base64.b64decode(request.message.data)
        decoded_str = decoded_bytes.decode("utf-8")
        payload_dict = json.loads(decoded_str)
        
        # 2. Validate using Pydantic
        incoming_msg = IncomingMessage(**payload_dict)
        logger.info(f"\n[Processing] Message from {incoming_msg.sender_info}: {incoming_msg.text}")
        
        # 3. Process the AI Logic
        outgoing_msg = await process_message(incoming_msg)
        
        # 4. Push final response back to GCP Pub/Sub Outgoing Topic
        await publish_outgoing_message(outgoing_msg)
        logger.info(f"[PUBLISH] Final Output: {outgoing_msg.response_text}")
        
        # 5. Return 200 OK. This tells Pub/Sub to DELETE the message from the queue (ACK).
        return Response(status_code=200)

    except ValidationError as e:
        logger.error(f"[Error] Invalid Payload structure: {e}")
        logger.error(f"[Error] Payload content: {payload_dict}")
        # Return 200 OK to drop bad payloads permanently. 
        # If we return 500, Pub/Sub will retry this broken JSON endlessly.
        return Response(status_code=200) 
        
    except Exception as e:
        logger.error(f"[Error] Processing failed: {e}")
        # Return 500. This tells Pub/Sub "Something temporarily broke, keep the message and try again later!" (NACK)
        raise HTTPException(status_code=500, detail="Internal Server Error")
    