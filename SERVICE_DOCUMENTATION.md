# AI-Orchestrator-Service: Architecture & Developer Guide

## 1. Overview & Purpose
The **AI-Orchestrator-Service** is the central "brain" of the Agents Platform. It acts as the middleware that connects user inputs (from platforms like WhatsApp or Telegram, ...) to the AI models (Google Gemini, ...). 

Its primary responsibility is to fetch agent configurations, retrieve chat history, process media files (voice, images), dynamically decide if it needs to query company knowledge bases (RAG), generate a response, log the interaction, and dispatch the final answer back to the user.

---

## 2. Core Technologies & Stack
* **Framework:** **FastAPI** (Python 3.13) - Provides a fast, asynchronous foundation.
* **Package Manager:** **uv** - Used for lightning-fast dependency resolution and installation.
* **AI & LLM:** **Google GenAI SDK (Gemini)** - Powers the core conversational intelligence, image summarization, and function calling (Tools).
* **Database:** **PostgreSQL** (via **SQLAlchemy** & **Alembic**) - Stores chat histories and media summaries.
* **Caching:** **Redis** - Caches agent configurations to prevent hammering the Core Platform DB on every message.
* **Messaging:** **GCP Pub/Sub** - Handles asynchronous message dispatching back to the gateways (WhatsApp/Telegram, ...) with strict ordering.
* **Cloud Storage:** **Google Cloud Storage (GCS)** - Used to download user-sent media files for AI processing.
* **Containerization:** **Docker** - Lightweight Python slim images optimized for fast builds and Cloud Run deployments.

---

## 3. Core Workflows (How it Works)

### A. Message Ingestion & Preparation
1. **Trigger:** A request arrives containing an `IncomingMessage` payload (Platform, sender ID, agent ID, text, media URL).
2. **Config Fetching:** The system checks **Redis** for the requested agent's configuration (system prompt, temperature, connected KB). If it misses, it fetches it from the Core Platform API and caches it for 5 minutes.
3. **History Retrieval:** Recent chat turns for this specific user/agent combo are pulled from PostgreSQL to give the LLM context.

### B. Media Handling (`services/media_processor.py`)
* **Voice Notes:** Downloaded from GCS and transcribed to text before sending to the LLM.
* **Images:** Intercepted and attached as binary parts to the Gemini request. In the background, a separate asynchronous task summarizes the image and updates the DB so future chat turns don't need to re-process the heavy image payload.

### C. The Intelligence Loop (`services/core_ai_logic.py`)
* **Tool Injection:** If the agent config includes a `kb_id` (Knowledge Base), a `search_company_knowledge_base` tool is injected into the Gemini configuration alongside strict prompt rules.
* **Execution Loop:** The system enters a retry loop. It calls Gemini. 
* **RAG Interception:** If Gemini decides it needs more info, it returns a "Function Call". The Orchestrator halts, securely calls the `RAG-Engine-Service` via HTTP, formats the document excerpts, and feeds them back to Gemini.
* **Final Generation:** Gemini generates a final conversational response based on the fetched data.

### D. Dispatch & Cleanup
1. **Database:** The user's query and the AI's final response are saved to the `ChatTurn` table.
2. **Pub/Sub:** The outgoing message is published to the GCP `outgoing_messages` topic. It uses a strict `ordering_key` (e.g., `whatsapp:12345:agentX`) to ensure messages arrive on the user's phone in the exact order they were generated.

---

## 4. Edge Cases & Resilience (Already Handled)
* **Redis/Core API Fallback:** If the config isn't in Redis, it smoothly fetches it from the primary API.
* **RAG Microservice Failures:** If the `RAG-Engine-Service` times out, throws a 404, or goes offline, the Orchestrator intercepts the HTTP error and translates it into a "System Note" for the LLM (e.g., *"System Note: The knowledge base search timed out"*), allowing the AI to apologize gracefully instead of crashing the app.
* **Infinite Loop Prevention:** The AI tool-calling loop is capped by `max_loops`. If the AI keeps searching fruitlessly, the orchestrator forces a final text summary on the last loop to guarantee the user gets a reply.
* **API Rate Limits:** Implements a graceful `asyncio.sleep()` retry mechanism if the Gemini API is overloaded.
* **Media Without Text:** If a user sends just an image or document with no caption, a fallback text (`[User sent a media file without text]`) is injected to maintain the LLM's expected text/image schema.

---

## 5. Future Development & Advanced Features Roadmap
To take this orchestrator from "good" to "world-class," consider implementing the following advanced features:

### A. Advanced Conversational Memory (Vector History)
* **Current State:** We load the last *N* messages (e.g., last 10 messages). If a user references something from 2 weeks ago, the bot forgets.
* **Future Feature:** Implement a "Mem0" or Vector-based memory system. Summarize user preferences (e.g., "User likes red cars", "User speaks French") and store them as vectors. Inject these dynamically into the system prompt to create a hyper-personalized, long-term memory agent.

### B. Multi-Agent Routing (Agent Handoffs)
* **Current State:** One agent handles the whole conversation.
* **Future Feature:** Implement a "Supervisor" router. If the customer asks for a refund, the AI detects the intent and silently transfers the chat context to a highly specialized "Billing Agent" LLM, seamlessly handing the conversation back and forth.

### C. LLM Observability & Tracing
* **Current State:** Standard Python logging.
* **Future Feature:** Integrate **Langfuse**, **LangSmith**, or **Phoenix Arize**. This will give you a beautiful dashboard to see exactly what prompts were sent to Gemini, how long the RAG tool took to execute, and how many tokens were consumed per chat, allowing for precise cost tracking and prompt debugging.

### D. Streaming Responses via WebSockets / Server-Sent Events (SSE)
* **Current State:** The system waits for the full final response before publishing to Pub/Sub.
* **Future Feature:** If you ever expand from WhatsApp/Telegram to a Web Chat widget, update `core_ai_logic.py` to use Gemini's streaming capabilities. You can stream tokens to the frontend in real-time, drastically reducing the perceived latency for the user.

### E. Human-in-the-Loop (HITL) Escalation
* **Current State:** AI answers everything or says "I don't know."
* **Future Feature:** Give the LLM a new tool called `escalate_to_human`. If the user is very angry (detected via sentiment) or the RAG fails completely, the AI triggers this tool, which pauses the AI's responses and flags the chat in a dashboard for a human customer support agent to take over.