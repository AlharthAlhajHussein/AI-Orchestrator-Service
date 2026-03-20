# test_pubsub.py
import asyncio
import base64
import httpx
from models.in_out_messages import IncomingMessage, PlatformType

async def simulate_pubsub_push():
    # url = "https://ai-orchestrator-api-173690049028.europe-west4.run.app/pubsub/push"
    url = "http://localhost:5001/pubsub/push"
    print("--- Simulating GCP Pub/Sub Push ---")

    # 1. Create our raw IncomingMessage
    raw_message = IncomingMessage(
        platform=PlatformType.TELEGRAM,
        sender_info={"id": 12345, "username":"AlharthAlhajHussein"},
        destination_agent_id="agent-1",
        text="ما هي ساعات العمل مواعيد العمل الرسمية لشركتكم؟"
    )

    # 2. Serialize to JSON string
    json_string = raw_message.model_dump_json()

    # 3. Base64 encode it (Exactly what GCP Pub/Sub does)
    encoded_bytes = base64.b64encode(json_string.encode("utf-8"))
    encoded_string = encoded_bytes.decode("utf-8")

    # 4. Wrap it in the official Pub/Sub Envelope format
    pubsub_envelope = {
        "message": {
            "data": encoded_string,
            "messageId": "mock-pubsub-id-999"
        }
    }

    # 5. Fire the HTTP POST request to your local FastAPI server
    print(f"Sending push request to {url}...")
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, json=pubsub_envelope)
        
        print(f"Response Status Code: {response.status_code}")
        if response.status_code == 200:
            print("Success! FastAPI returned 200 OK (Pub/Sub will ACK and delete the message).")
        else:
            print("Failed! FastAPI returned an error (Pub/Sub will NACK and retry later).")

if __name__ == "__main__":
    asyncio.run(simulate_pubsub_push())