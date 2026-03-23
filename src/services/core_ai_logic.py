
import asyncio
import uuid
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


# --- Your Core Logic ---
async def process_message(incoming_msg: IncomingMessage) -> OutgoingMessage:
    """The core orchestrator logic."""
    logger.info(f"[Redis or Request] Getting agent config for {incoming_msg.destination_agent_id}")
    config = await get_agent_config(incoming_msg.destination_agent_id)
    
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
    for attempt in range(max_loops):
        logger.info(f"[Gemini] Executing call (Attempt {attempt + 1}/{max_loops})...")
        
        try:
            response = await gemini_client.aio.models.generate_content(
                model=config.model_type,
                contents=messages,
                config=genai_config
            )
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

    return OutgoingMessage(
        platform=incoming_msg.platform,
        sender_info=incoming_msg.sender_info,
        destination_agent_id=incoming_msg.destination_agent_id,
        response_text=final_response_text
    )
