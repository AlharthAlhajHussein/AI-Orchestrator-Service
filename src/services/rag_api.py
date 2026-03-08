import httpx
from helpers import settings
import logging 

logger = logging.getLogger("uvicorn.error")

async def search_company_knowledge_base(query: str, kb_id: str) -> str:
    """
    Calls the RAG Service to perform a vector search.
    Returns a formatted string of the best chunks.
    """
    logger.info(f"[Tool Execution] RAG searching for: '{query}' in KB: {kb_id}")
    
    async with httpx.AsyncClient() as client:
        try:
            # Example HTTP call to your RAG API
            # response = await client.post(
            #     f"{settings.rag_api_url}/api/search", 
            #     json={"query": query, "kb_id": kb_id}
            # )
            # data = response.json()
            
            # MOCKING THE RAG RESPONSE FOR TESTING:
            mock_chunks = [
                "Our business hours are Monday to Friday, 11 AM to 6 PM.",
                "The refund policy allows returns within 30 days of purchase.",
                "We offer free shipping on all orders over $50.",
                "Our company was founded in 2010 and has been growing ever since.",
                "The latest product release was in March 2024, called 'Product X'."
            ]
            
            if not mock_chunks:
                return "No relevant information found in the documents."
                
            # Combine the chunks into a single text block for the LLM to read
            return "\n\n".join(mock_chunks)
            
        except Exception as e:
            logger.error(f"[RAG Error] Failed to contact RAG Service: {e}")
            return "Error accessing the knowledge base."
        

                