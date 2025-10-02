import asyncpg
from .config import settings

class Database:
    def __init__(self):
        self.pool = None
    
    async def connect(self):
        """Create the connection pool"""
        self.pool = await asyncpg.create_pool(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password,
            database=settings.db_name,
            ssl=settings.db_sslmode,
            min_size=5,
            max_size=20,
            command_timeout=60
        )
        print(f"Database pool created: {settings.db_name}@{settings.db_host}")

    async def disconnect(self):
        """Close the connection pool"""
        if self.pool:
            await self.pool.close()
            print("Database pool closed.")

    async def fetch_one(self, query: str, *args):
        """Fetch a single row"""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
        
    async def fetch_all(self, query: str, *args):
        """Fetch multiple rows"""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)
        
    async def execute(self, query: str, *args):
        """Execute a query without returning results"""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

db = Database()
