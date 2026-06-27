import asyncio
import httpx

async def check_trivy():
    proc = await asyncio.create_subprocess_exec(
        "docker", "run", "--rm", "aquasec/trivy:latest", "image", "-f", "json", "--quiet", "wordpress:latest",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    print(proc.returncode)
    print(stderr.decode())
    if stdout:
        import json
        try:
            data = json.loads(stdout.decode())
            print("Loaded JSON, results:", len(data.get("Results", [])))
        except Exception as e:
            print("Failed to load JSON", e)

asyncio.run(check_trivy())
