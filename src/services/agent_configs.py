import json
import httpx
from pydantic import BaseModel
from models.redis_setup import redis_client
import logging 

logger = logging.getLogger("uvicorn.error")

class AgentConfig(BaseModel):
    system_prompt: str
    model_type: str
    temperature: float
    company_id: str
    kb_id: str | None = None # Knowledge Base ID
    

async def get_agent_config(agent_id: str) -> AgentConfig:
    """Fetches config from Redis, or falls back to the Core API if missing."""
    cache_key = f"agent_config:{agent_id}"
    
    # 1. Try Redis First
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        logger.info(f"[Cache Hit] Loaded config for {agent_id} from Redis.")
        return AgentConfig(**json.loads(cached_data))
    
    # 2. Cache Miss: Talk to the Core Platform API
    logger.info(f"[Cache Miss] Fetching config for {agent_id} from Core API...")
    async with httpx.AsyncClient() as client:
        # Note: In reality, replace this URL with your actual Core API endpoint
        # response = await client.get(f"{settings.core_api_url}/api/agents/{agent_id}")
        

        # If your API was ready, you'd do: mock_api_data = response.json()
        # --- MOCKING THE CORE API RESPONSE ---
        # This represents what the COMPANY typed into your dashboard
        company_base_prompt = """
            You are the official Customer Support AI Agent for "Alhaj Hussein". You are interacting with customers via WhatsApp and Telegram.
            Your goal is to provide helpful, accurate, and concise answers to customer questions and in the same language as the user asked you.
        """
        # company_base_prompt = "أنت أسمك أحمد وانت مسؤال دعم العملاء في شركة الحاج حسين. إذا سأل المستخدم أي سؤال ليس لديك معلومات كافية للإجابة عليه، فقط قل 'عذرًا، لا أعرف'. ملاحظة مهمة جدًا: دائمًا أجب بنفس اللغة التي يتحدث بها المستخدم. كن مهذبًا وموجزًا."
        company_id = "Alhaj_Hussein"
        # Change this to None to test an agent without a Knowledge Base!
        linked_kb_id = "40509a16-41ff-4b10-90c8-cac9bb07554f"
        
        # 3. DYNAMIC PROMPT ASSEMBLY
        final_system_prompt = company_base_prompt
        
        if linked_kb_id:
            # If they attached a bucket, we silently inject our platform's strict RAG rules
            rag_rules = (
                "\n\n--- STRICT KNOWLEDGE BASE SEARCH RULES ---\n"
                "1. Always use the `search_company_knowledge_base` tool to find information if you need data before answering, also check the previous chat history for getting data.\n"
                "2. If the tool returns data that does NOT answer the user's question, call the tool again using DIFFERENT search keywords. You can try multiple times.\n"
                "3. PARTIAL ANSWERS: If the user asks multiple questions and you can only find answers to some of them, answer what you know. For the missing parts, explicitly state: 'I don't have information on that specific part.'\n"
                "4. TOTAL FAILURE: If you cannot find ANY answers to ANY part of the user's prompt, output this exact phrase and nothing else: 'I'm sorry, I don't have information on that.'"
            )
            final_system_prompt += rag_rules

        mock_api_data = {
            "system_prompt": final_system_prompt,
            "model_type": "gemini-2.5-pro",
            "temperature": 0.1,
            "company_id": company_id,
            "kb_id": linked_kb_id
        }

        config = AgentConfig(**mock_api_data)
        
        # 3. Save to Redis with a Time-To-Live (TTL) of 5 minutes (300 seconds)
        await redis_client.setex(cache_key, 300, config.model_dump_json())
        return config
    