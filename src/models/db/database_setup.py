# database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from helpers import settings
# Connect to the local PostgreSQL container you spun up in Phase 1
DATABASE_URL = f"postgresql+asyncpg://{settings.db_user}:{settings.db_password}@{settings.db_host}:{settings.db_port}/{settings.db_name}"

# The Engine manages the connection pool
engine = create_async_engine(DATABASE_URL, echo=False) # Set echo=True to see raw SQL in the console

# The SessionLocal is a factory that generates new database sessions
SessionLocal = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# Dependency function to get a database session
async def get_db():
    async with SessionLocal() as session:
        yield session
        