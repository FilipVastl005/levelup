import asyncio
from services.db import init_db, db_register
import os

async def main():
    if os.path.exists('/app/data/levelup.db'):
        os.remove('/app/data/levelup.db')
    await init_db()
    res = await db_register("test@test.com", "mypass", "testuser")
    print(res)

asyncio.run(main())
