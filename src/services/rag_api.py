import httpx
import logging
from helpers.config import settings

logger = logging.getLogger("uvicorn.error")

async def search_company_knowledge_base(company_id: str, kb_id: str, query: str) -> str:
    """
    Calls the RAG Service to perform a vector search.
    Returns a cleanly formatted string of the best chunks for the LLM to read.
    """
    logger.info(f"[Tool Execution] RAG searching for: '{query}' in KB: {kb_id} for Company: {company_id}")
    
    # 1. Construct the exact URL to your new RAG Service
    # Make sure settings.rag_api_url is set to "http://127.0.0.1:5000" in your local Orchestrator .env
    rag_service_url = f"{settings.rag_api_url}/api/v1/search/{company_id}/{kb_id}"
    
    headers = {"X-Internal-Secret": settings.internal_secret_between_services}
    # 2. EDGE CASE: Enforce strict timeouts. internal_secret_between_services
    # If the RAG DB is locked, we don't want the WhatsApp bot to hang forever.
    timeout = httpx.Timeout(20.0, connect=5.0)
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            # 3. Fire the request matching your SearchRequest schema
            response = await client.post(
                rag_service_url, 
                headers=headers,
                json={
                    "query": query, 
                    "top_k": 5  # Give the LLM the top 2 most relevant paragraphs
                }
            )
            
            # 4. EDGE CASE: Handle specific expected HTTP errors natively
            if response.status_code == 404:
                logger.warning(f"Knowledge Base {kb_id} not found or unauthorized.")
                # We return a plain string so the LLM knows what happened and can tell the user politely
                return "System Note: The requested knowledge base does not exist or is empty."
            
            if response.status_code == 422:
                logger.error(f"Validation Error sending data to RAG: {response.text}")
                return "System Note: Invalid search query format."

            # Throw an exception for any other 500-level crashes
            response.raise_for_status() 
            
            # 5. Parse the successful response
            data = response.json()
            results = data.get("results", [])
            
            # 6. EDGE CASE: No relevant chunks found (Similarity score was too low)
            if not results:
                return "System Note: No relevant information found in the company documents to answer this specific query."
            
            # 7. Format the chunks beautifully for the LLM's context window
            formatted_chunks = []
            for i, item in enumerate(results, 1):
                chunk_text = item.get("chunk_text", "").strip()
                # Optional: You can include the similarity score in the prompt if you want the LLM to know how confident the search was!
                score = item.get("similarity_score", 0.0)
                
                if chunk_text:
                    formatted_chunks.append(f"--- Document Excerpt {i} (Relevance: {score}) ---\n{chunk_text}")
            
            return "\n\n".join(formatted_chunks)
            
        # 8. EDGE CASE: Massive network failures
        except httpx.ConnectError:
            logger.error("[RAG Error] Could not connect to the RAG Service. Is it running?")
            return "System Note: The company knowledge base service is currently offline."
        except httpx.TimeoutException:
            logger.error("[RAG Error] RAG Service took too long to respond.")
            return "System Note: The knowledge base search timed out."
        except Exception as e:
            logger.error(f"[RAG Error] Unexpected error contacting RAG Service: {e}")
            return "System Note: An unexpected error occurred while searching the documents."