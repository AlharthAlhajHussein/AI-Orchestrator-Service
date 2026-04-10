import json
import httpx
from pydantic import BaseModel
from fastapi import HTTPException
from models.redis_setup import redis_client
from helpers import settings
import logging 

logger = logging.getLogger("uvicorn.error")

class AgentConfig(BaseModel):
    system_prompt: str
    model_type: str
    temperature: float
    company_id: str
    kb_id: str | None = None # Maps to rag_container_id from Core Platform
    

async def get_agent_config(agent_id: str) -> AgentConfig:
    """Fetches config from Redis, or falls back to the Core API if missing."""
    cache_key = f"agent_config:{agent_id}"
    
    # 1. Try Redis First
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        logger.info(f"[Cache Hit] Loaded config for {agent_id} from Redis.")
        return AgentConfig(**json.loads(cached_data))
    
    # 2. Cache Miss: Fetch config securely from the Core Platform API
    logger.info(f"[Cache Miss] Fetching config for {agent_id} from Core API...")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                f"{settings.core_api_url}/internal/agents/config",
                params={"agent_id": agent_id},
                headers={"X-Internal-Secret": settings.internal_secret_between_services}
            )
            
            if response.status_code == 404:
                raise ValueError("Agent not found in the Core Platform.")
                
            response.raise_for_status()
            data = response.json()
            
            if not data.get("is_active", True):
                raise ValueError("Agent is currently marked as inactive.")

            # 3. DYNAMIC PROMPT ASSEMBLY
            base_prompt = data.get("system_prompt") or "You are a helpful AI assistant."
            final_system_prompt = base_prompt
            
            linked_kb_id = data.get("rag_container_id")
            
            if linked_kb_id:
                # If they attached a bucket to this agent, we silently inject our platform's strict RAG rules
                rag_rules = (
                    "\n\n--- STRICT KNOWLEDGE BASE SEARCH RULES ---\n"
                    "1. Always use the `search_company_knowledge_base` tool to find information if you need data before answering, also check the previous chat history for getting data.\n"
                    "2. If the tool returns data that does NOT answer the user's question, call the tool again using DIFFERENT search keywords. You can try multiple times.\n"
                    "3. PARTIAL ANSWERS: If the user asks multiple questions and you can only find answers to some of them, answer what you know. For the missing parts, explicitly state: 'I don't have information on that specific part.'\n"
                    "4. TOTAL FAILURE: If you cannot find ANY answers to ANY part of the user's prompt, output this exact phrase and nothing else: 'I'm sorry, I don't have information on that.'"
                )
                final_system_prompt += rag_rules

            config = AgentConfig(
                system_prompt=final_system_prompt,
                model_type=data.get("model_type"),
                temperature=float(data.get("temperature")),
                company_id=str(data.get("company_id")),
                kb_id=linked_kb_id
            )
            
            # 4. Save to Redis with a Time-To-Live (TTL) of 5 minutes (300 seconds)
            await redis_client.setex(cache_key, 300, config.model_dump_json())
            return config
            
        except httpx.HTTPStatusError as e:
            logger.error(f"[Core API Error] Failed to fetch config for {agent_id}. Status: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"[Core API Connection Error] Could not connect to Core Platform: {e}")
            raise RuntimeError("Internal Core Platform is unreachable.")
        