import json
import asyncio
from google.cloud import pubsub_v1
from helpers import settings
from models.in_out_messages import OutgoingMessage # You can rename this file later!
import logging 

logger = logging.getLogger("uvicorn.error")

# Initialize the GCP Publisher Client
publisher = pubsub_v1.PublisherClient()

# Create the full path to your topic
topic_path = publisher.topic_path(settings.gcp_project_id, "outgoing_messages")

async def publish_outgoing_message(message: OutgoingMessage):
    """Publishes the final AI response to the GCP Pub/Sub topic."""
    
    # Convert Pydantic model to JSON string, then encode to bytes (required by Pub/Sub)
    data_bytes = message.model_dump_json().encode("utf-8")
    
    # Publish returns a 'Future' (a promise). We wrap it to work cleanly with asyncio.
    future = publisher.publish(topic_path, data=data_bytes)
    
    # Await the result to ensure it was successfully sent
    message_id = await asyncio.wrap_future(future)
    logger.info(f"[Pub/Sub] Published outgoing message with ID: {message_id}")
    return message_id