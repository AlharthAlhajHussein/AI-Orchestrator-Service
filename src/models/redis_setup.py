import redis.asyncio as redis
from helpers import settings

redis_client = redis.from_url(f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}", 
                              decode_responses=True)

