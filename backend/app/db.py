"""Koneksi database yang sabar: menunggu PostgreSQL siap (mis. saat Raspi baru boot)."""
import asyncio
import os

import asyncpg


async def create_pool(min_size=1, max_size=3, attempts=60, delay=2):
    for i in range(1, attempts + 1):
        try:
            return await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=min_size, max_size=max_size)
        except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError) as e:
            print(f"Database belum siap ({e.__class__.__name__}), coba lagi {i}/{attempts}...", flush=True)
            await asyncio.sleep(delay)
    raise RuntimeError("Database tidak bisa dihubungi")
