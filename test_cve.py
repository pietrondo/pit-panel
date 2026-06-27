import asyncio
import httpx

async def get_cve():
    async with httpx.AsyncClient() as client:
        req = {
            "version": "5.5.0",
            "package": {"name": "wordpress", "ecosystem": "Packagist"}
        }
        res = await client.post("https://api.osv.dev/v1/query", json=req)
        print(res.status_code)
        if res.status_code == 200:
            data = res.json()
            vulns = data.get("vulns", [])
            print(f"Found {len(vulns)} vulnerabilities")
            if vulns:
                for v in vulns[:5]:
                    print(v.get("id"), v.get("summary") or v.get("details")[:50])

asyncio.run(get_cve())
