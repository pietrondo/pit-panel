import asyncio
import time
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from pit_panel.db.models import Base
from pit_panel.security.ipban import ban_ip, ban_ips_bulk

async def setup_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return engine, SessionLocal

async def run_benchmark():
    engine, SessionLocal = await setup_db()

    ips = [f"192.168.1.{i}" for i in range(1, 201)]

    # Benchmark N+1
    async with SessionLocal() as db:
        start = time.time()
        for ip in ips:
            await ban_ip(db, ip, "test_n1", 10080)
        n1_time = time.time() - start

    print(f"N+1 approach (ban_ip loop): {n1_time:.4f} seconds")

    # Clear DB
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Benchmark Bulk
    async with SessionLocal() as db:
        start = time.time()
        await ban_ips_bulk(db, ips, "test_bulk", 10080)
        bulk_time = time.time() - start

    print(f"Bulk approach (ban_ips_bulk): {bulk_time:.4f} seconds")
    print(f"Improvement: {n1_time / bulk_time:.2f}x faster")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
