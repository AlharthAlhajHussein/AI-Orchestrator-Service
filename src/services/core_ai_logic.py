
import asyncio
import uuid
import httpx
from datetime import datetime, timezone
from google import genai
from google.genai import types

from helpers import settings
from models.in_out_messages import IncomingMessage, OutgoingMessage, MessageType
from services.agent_configs import get_agent_config
from services.rag_api import search_company_knowledge_base
from services.media_processor import download_gcs_media, transcribe_voice, summarize_image_with_gemini
from models.db.database_setup import SessionLocal
from models.db.db_operations import get_recent_history, save_chat_turn, update_chat_turn_media_summary
import logging 

logger = logging.getLogger("uvicorn.error")

async def background_summarize_image(turn_id: uuid.UUID, image_bytes: bytes, mime_type: str, agent_role: str):
    """Runs in the background after the user gets a response to save DB tokens for future chats."""
    logger.info(f"[Background Task] Summarizing image for turn {turn_id}...")
    summary = await summarize_image_with_gemini(image_bytes, agent_role, mime_type)
    async with SessionLocal() as db_session:
        await update_chat_turn_media_summary(db_session, turn_id, summary)
    logger.info(f"[Background Task] Image summarization saved for turn {turn_id}.")

async def sync_interaction_to_core(payload: dict):
    """Fires a non-blocking HTTP request to sync the conversation data to the Core Platform."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{settings.core_api_url}/internal/interactions/sync",
                json=payload,
                headers={"X-Internal-Secret": settings.internal_secret_between_services}
            )
    except Exception as e:
        logger.error(f"[Sync Error] Failed to sync interaction to Core Platform: {e}")

# --- Your Core Logic ---
async def process_message(incoming_msg: IncomingMessage) -> OutgoingMessage:
    """The core orchestrator logic."""
    try:
        logger.info(f"[Redis or Request] Getting agent config for {incoming_msg.destination_agent_id}")
        config = await get_agent_config(str(incoming_msg.destination_agent_id))
    except ValueError as e:
        logger.warning(f"[Agent Config Warning] {e} Aborting processing.")
        return OutgoingMessage(
            platform=incoming_msg.platform,
            sender_info=incoming_msg.sender_info,
            destination_agent_id=incoming_msg.destination_agent_id,
            response_text="System Note: This AI agent is currently inactive or unavailable."
        )
    
    logger.info(f"[DB] Getting recent history for {incoming_msg.destination_agent_id}")
    async with SessionLocal() as db_session:
        history_turns = await get_recent_history(
            db_session,
            incoming_msg.destination_agent_id,
            incoming_msg.platform,
            incoming_msg.sender_info,
            limit=settings.chat_history_limit
        )
    logger.info(f"[DB] Retrieved {len(history_turns)} from DB.")
    messages = []
    for turn in history_turns:
        # Safely handle nullable user_message for historical turns
        if turn.user_message:
            messages.append(types.Content(role="user", parts=[types.Part.from_text(text=turn.user_message)]))
        else:
            fallback_text = turn.media_summary if turn.media_summary else "[User sent a media file without text]"
            messages.append(types.Content(role="user", parts=[types.Part.from_text(text=fallback_text)]))
            
        messages.append(types.Content(role="model", parts=[types.Part.from_text(text=turn.ai_response)]))
        
    # 1. Intercept Media and perform necessary conversions
    original_text = incoming_msg.text  # Capture exactly what the user sent before we mutate it
    
    media_bytes = None
    mime_type = "application/octet-stream"

    if incoming_msg.media_url:
        media_bytes = await download_gcs_media(incoming_msg.media_url)
        if incoming_msg.message_type == MessageType.VOICE:
            mime_type = "audio/ogg"
        elif incoming_msg.message_type in [MessageType.IMAGE, MessageType.TEXT_AND_IMAGE]:
            mime_type = "image/jpeg"

    if incoming_msg.message_type == MessageType.VOICE and media_bytes:
        incoming_text = await transcribe_voice(media_bytes, mime_type)
        incoming_msg.text = incoming_text  # Overwrite so it gets saved to the DB correctly
    else:
        incoming_text = incoming_msg.text if incoming_msg.text else "[User sent a media file without text]"
        
    current_user_parts = [types.Part.from_text(text=incoming_text)]
    if media_bytes and incoming_msg.message_type in [MessageType.IMAGE, MessageType.TEXT_AND_IMAGE]:
        current_user_parts.insert(0, types.Part.from_bytes(data=media_bytes, mime_type=mime_type))
        
    messages.append(types.Content(role="user", parts=current_user_parts))
    
    rag_tool = types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="search_company_knowledge_base",
                description="Use this tool if you need specific company information to answer the user.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={"query": types.Schema(type=types.Type.STRING, description="The search query")},
                    required=["query"],
                ),
            )
        ]
    )
    
    active_tools = [rag_tool] if config.kb_id else None
    max_loops = settings.llm_max_rag_tool_retries if config.kb_id else 1
    final_response_text = "I'm sorry, I don't have information on that." if config.kb_id else "I couldn't generate a response." 
    
    genai_config = types.GenerateContentConfig(
        system_instruction=config.system_prompt,
        temperature=config.temperature,
        tools=active_tools
    )
    
    gemini_client = genai.Client(api_key=settings.gemini_api_key)
    
    api_error = False
    total_tokens_used = 0
    for attempt in range(max_loops):
        logger.info(f"[Gemini] Executing call (Attempt {attempt + 1}/{max_loops})...")
        
        try:
            response = await gemini_client.aio.models.generate_content(
                model=config.model_type,
                contents=messages,
                config=genai_config
            )
            # Accumulate token usage for accurate SaaS Billing
            if response.usage_metadata:
                total_tokens_used += response.usage_metadata.total_token_count
                
        except Exception as e:
            logger.error(f"[Gemini Error] API call failed on attempt {attempt+1}: {e}")
            if attempt == max_loops - 1:
                api_error = True
            await asyncio.sleep(attempt)
            continue
        
        logger.info(f"*************************************************************")
        logger.info(f"Messages: {[part.text if part.text else '<MEDIA_BYTES>' for msg in messages for part in msg.parts]}")
        logger.info(f"*************************************************************")
        
        if response.function_calls:
            function_call = response.function_calls[0]
            if function_call.name == "search_company_knowledge_base":
                search_query = function_call.args["query"]
                
                rag_result = await search_company_knowledge_base(config.company_id, config.kb_id, search_query)
                
                messages.append(types.Content(role="model", parts=[types.Part.from_function_call(
                    name=function_call.name, args=function_call.args
                )]))
                messages.append(types.Content(role="user", parts=[types.Part.from_function_response(
                    name=function_call.name, response={"result": rag_result}
                )]))
                
                if attempt == max_loops - 1:
                    logger.info(f"[Gemini] Max retries reached. Forcing final text summary...")
                    messages.append(types.Content(role="user", parts=[types.Part.from_text(
                        text="SYSTEM MESSAGE: You have run out of time to search. You must now generate a final text response answering the user based ONLY on the information you have gathered so far. Provide partial answers if necessary."
                    )]))
                    genai_config.tools = None 
                    try:
                        final_response = await gemini_client.aio.models.generate_content(
                            model=config.model_type,
                            contents=messages,
                            config=genai_config
                        )
                    except Exception as force_e:
                        logger.error(f"[Gemini Error] Failed forced summary: {force_e}")
                        api_error = True
                        break
                        
                    if final_response.text:
                        final_response_text = final_response.text
                    break 
                continue 
        
        if response.text:
            final_response_text = response.text
            break
            
    if api_error:
        final_response_text = "I am currently experiencing a high volume of requests. Please wait a moment and try again."

    async with SessionLocal() as db_session:
        saved_turn = await save_chat_turn(
            db_session, 
            incoming_msg.destination_agent_id,
            incoming_msg.platform, 
            incoming_msg.sender_info, 
            incoming_msg.text, 
            final_response_text,
            incoming_msg.timestamp,
            message_type=incoming_msg.message_type.value,
            media_url=incoming_msg.media_url
        )
        
    # Background Image Summarization triggers after DB insertion
    if media_bytes and incoming_msg.message_type in [MessageType.IMAGE, MessageType.TEXT_AND_IMAGE]:
        asyncio.create_task(
            background_summarize_image(
                saved_turn.id, media_bytes, mime_type, config.system_prompt
            )
        )

    # Background task: Sync interaction to the Core Platform for Dashboard & Billing
    # We safely extract the sender's ID whether the gateway sent a dictionary or a direct string
    if isinstance(incoming_msg.sender_info, dict):
        # Safely extract Telegram's numeric ID or username, or WhatsApp's sender string
        sender_id_str = str(incoming_msg.sender_info.get("id", incoming_msg.sender_info.get("username", incoming_msg.sender_info)))
    else:
        sender_id_str = str(incoming_msg.sender_info)
        
    # Map Orchestrator's internal message types to Core Platform's expected types
    core_message_type = "text"
    sync_user_text = original_text

    if incoming_msg.message_type == MessageType.VOICE:
        core_message_type = "audio"
        sync_user_text = None
    elif incoming_msg.message_type == MessageType.IMAGE:
        core_message_type = "image"
        sync_user_text = None
    elif incoming_msg.message_type == MessageType.TEXT_AND_IMAGE:
        core_message_type = "image"
        sync_user_text = original_text
    
    sync_payload = {
        "company_id": config.company_id,
        "agent_id": incoming_msg.destination_agent_id,
        "platform": incoming_msg.platform.value,
        "sender_id": sender_id_str,
        "tokens_used": total_tokens_used,
        "user_message": {
            "message_type": core_message_type,
            "media_url": incoming_msg.media_url,
            "message_time": incoming_msg.timestamp.isoformat(),
            "text": sync_user_text
        },
        "ai_response": {
            "message_type": "text",
            "media_url": None,
            "message_time": datetime.now(timezone.utc).isoformat(),
            "text": final_response_text
        }
    }
    asyncio.create_task(sync_interaction_to_core(sync_payload))

    return OutgoingMessage(
        platform=incoming_msg.platform,
        sender_info=incoming_msg.sender_info,
        destination_agent_id=incoming_msg.destination_agent_id,
        response_text=final_response_text
    )
