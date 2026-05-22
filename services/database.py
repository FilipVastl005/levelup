import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

# Make sure directory exists
DATA_DIR = "/app/data"
os.makedirs(DATA_DIR, exist_ok=True)

SQLITE_URL = f"sqlite+aiosqlite:///{DATA_DIR}/levelup.db"

engine = create_async_engine(
    SQLITE_URL,
    echo=False,
    connect_args={"check_same_thread": False}
)

async def get_session() -> AsyncSession:
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
