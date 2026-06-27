import asyncio
import httpx

async def check_osv():
    async with httpx.AsyncClient() as client:
        # Check a specific package, e.g., wordpress
        req = {
            "package": {"name": "wordpress", "ecosystem": "Packagist"},
            "version": "6.0.0"
        }
        res = await client.post("https://api.osv.dev/v1/query", json=req)
        print(res.status_code)
        print(res.json())

asyncio.run(check_osv())
