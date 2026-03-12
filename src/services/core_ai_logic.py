
from google import genai
from google.genai import types

from helpers import settings
from models.in_out_messages import IncomingMessage, OutgoingMessage
from services.agent_configs import get_agent_config
from services.rag_api import search_company_knowledge_base
from models.db.database_setup import SessionLocal
from models.db.db_operations import get_recent_history, save_chat_turn
import logging 

logger = logging.getLogger("uvicorn.error")



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
            incoming_msg.sender_id,
            limit=settings.chat_history_limit
        )
    logger.info(f"[DB] Retrieved {len(history_turns)} from DB.")
    messages = []
    for turn in history_turns:
        messages.append(types.Content(role="user", parts=[types.Part.from_text(text=turn.user_message)]))
        messages.append(types.Content(role="model", parts=[types.Part.from_text(text=turn.ai_response)]))
        
    messages.append(types.Content(role="user", parts=[types.Part.from_text(text=incoming_msg.text)]))
    
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
    
    for attempt in range(max_loops):
        logger.info(f"[Gemini] Executing call (Attempt {attempt + 1}/{max_loops})...")
        response = await gemini_client.aio.models.generate_content(
            model=config.model_type,
            contents=messages,
            config=genai_config
        )
        
        logger.info(f"*************************************************************")
        logger.info(f"Messages: {[part.text for msg in messages for part in msg.parts]}")
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
                    final_response = await gemini_client.aio.models.generate_content(
                        model=config.model_type,
                        contents=messages,
                        config=genai_config
                    )
                    if final_response.text:
                        final_response_text = final_response.text
                    break 
                continue 
        
        if response.text:
            final_response_text = response.text
            break

    async with SessionLocal() as db_session:
        await save_chat_turn(
            db_session, 
            incoming_msg.destination_agent_id,
            incoming_msg.platform, 
            incoming_msg.sender_id, 
            incoming_msg.text, 
            final_response_text,
            incoming_msg.timestamp
        )

    return OutgoingMessage(
        platform=incoming_msg.platform,
        sender_id=incoming_msg.sender_id,
        destination_agent_id=incoming_msg.destination_agent_id,
        response_text=final_response_text
    )

