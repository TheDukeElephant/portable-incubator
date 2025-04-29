import aiosqlite, os, pathlib
from .settings import settings

pathlib.Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)

async def init_db():
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS samples(
                              t REAL, temperature REAL, setpoint REAL)""")
        await db.commit()

async def log_sample(ts: float, temp: float, sp: float):
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("INSERT INTO samples VALUES (?,?,?)", (ts, temp, sp))
        await db.commit()
