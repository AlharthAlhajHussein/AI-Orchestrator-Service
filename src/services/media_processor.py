import asyncio
import httpx
import logging
import urllib.parse
from google import genai
from google.genai import types
from google.cloud import storage
from helpers.config import settings

logger = logging.getLogger("uvicorn.error")

async def download_gcs_media(media_url: str) -> bytes | None:
    """Downloads media securely from a GCS URI or HTTP URL."""
    try:
        if media_url.startswith("gs://"):
            parsed = urllib.parse.urlparse(media_url)
            bucket_name = parsed.netloc
            blob_name = parsed.path.lstrip("/")
            
            # Run synchronous GCS client in a thread pool to avoid blocking asyncio
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            return await asyncio.to_thread(blob.download_as_bytes)
        else:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(media_url)
                response.raise_for_status()
                return response.content
    except Exception as e:
        logger.error(f"[Media Processor] Failed to download media from {media_url}: {e}")
        return None

async def transcribe_voice(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """Uses Gemini models with fallback to Google Cloud Speech-to-Text for audio transcription."""
    client = genai.Client(api_key=settings.gemini_api_key)
    
    models_to_try = ['gemini-2.5-flash', 'gemini-1.5-flash-latest', 'gemini-2.5-pro']
    
    for model in models_to_try:
        for attempt in range(2):
            try:
                response = await client.aio.models.generate_content(
                    model=model,
                    contents=[
                        types.Content(role="user", parts=[
                            types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                            types.Part.from_text(text="Transcribe this audio precisely. Output ONLY the transcription in the original language, no extra commentary.")
                        ])
                    ]
                )
                if response.text:
                    return response.text
            except Exception as e:
                logger.warning(f"[STT Error] Model {model} attempt {attempt+1}/2 failed: {e}")
                await asyncio.sleep(1)
                
    logger.info("[STT Fallback] Gemini failed. Attempting Google Cloud Speech-to-Text...")
    try:
        from google.cloud import speech
        speech_client = speech.SpeechAsyncClient()
        audio = speech.RecognitionAudio(content=audio_bytes)
        
        # WhatsApp/Telegram voice notes are typically OGG_OPUS.
        # We set Arabic as primary, English as alternative to cover likely cases.
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
            sample_rate_hertz=48000,
            language_code="ar-SA",
            alternative_language_codes=["en-US", "ar-EG", "ar-AE"]
        )
        
        response = await speech_client.recognize(config=config, audio=audio)
        
        # If 48kHz fails (returns nothing), try 16kHz
        if not response.results:
            config.sample_rate_hertz = 16000
            response = await speech_client.recognize(config=config, audio=audio)
            
        if response.results:
            transcript = " ".join([res.alternatives[0].transcript for res in response.results])
            if transcript.strip():
                return transcript.strip()
    except ImportError:
        logger.error("[STT Fallback] 'google-cloud-speech' package is not installed.")
    except Exception as e:
        logger.error(f"[STT Fallback Error] Google Speech failed: {e}")
    
    return "[Voice message transcription failed due to high service load.]"

async def summarize_image_with_gemini(image_bytes: bytes, agent_role: str, mime_type: str = "image/jpeg") -> str:
    """Uses Gemini models with fallbacks to summarize images based on context."""
    client = genai.Client(api_key=settings.gemini_api_key)
    models_to_try = ['gemini-2.5-flash', 'gemini-1.5-flash-latest', 'gemini-2.5-pro']
    
    for model in models_to_try:
        for attempt in range(2):
            try:
                response = await client.aio.models.generate_content(
                    model=model,
                    contents=[
                        types.Content(role="user", parts=[
                            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                            types.Part.from_text(text=f"Describe this image concisely. Context: The user is talking to an AI agent with the following role: {agent_role}. Focus on details relevant to this role.")
                        ])
                    ]
                )
                if response.text:
                    return response.text
            except Exception as e:
                logger.warning(f"[Image Summarization Error] Model {model} attempt {attempt+1}/2 failed: {e}")
                await asyncio.sleep(1)
    
    return "[Image could not be summarized due to high service load.]"