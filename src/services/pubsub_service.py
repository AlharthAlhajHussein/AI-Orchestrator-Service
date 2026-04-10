import json
import asyncio
from google.cloud import pubsub_v1
from helpers import settings
from models.in_out_messages import OutgoingMessage # You can rename this file later!
import logging 

logger = logging.getLogger("uvicorn.error")

# Initialize the GCP Publisher Client
# 1. Enable message ordering here as well
publisher_options = pubsub_v1.types.PublisherOptions(enable_message_ordering=True)
publisher = pubsub_v1.PublisherClient(publisher_options=publisher_options)

# Create the full path to your topic
topic_path = publisher.topic_path(settings.gcp_project_id, "outgoing_messages")

async def publish_outgoing_message(message: OutgoingMessage):
    """Publishes the final AI response to the GCP Pub/Sub topic."""
    
    # Convert Pydantic model to JSON string, then encode to bytes (required by Pub/Sub)
    data_bytes = message.model_dump_json().encode("utf-8")
    
    # 2. Reconstruct the exact same ordering key
    chat_ordering_key = f"{message.platform.value}:{message.sender_info["id"]}:{message.destination_agent_id}"
    
    # 3. Publish with the key
    future = publisher.publish(
        topic_path, 
        data=data_bytes,
        ordering_key=chat_ordering_key
    )

    # Await the result to ensure it was successfully sent
    message_id = await asyncio.wrap_future(future)
    logger.info(f"[Pub/Sub] Published outgoing message ordered with ID: {message_id} with key: {chat_ordering_key}")
    return message_id