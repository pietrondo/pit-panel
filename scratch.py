import asyncio
import json

async def run_trivy():
    proc = await asyncio.create_subprocess_exec(
        "docker", "run", "--rm", "-v", "/var/run/docker.sock:/var/run/docker.sock", "aquasec/trivy:latest", "image", "-f", "json", "alpine:3.15",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    print("Return code:", proc.returncode)
    print("Stderr:", stderr.decode()[:200])
    if proc.returncode == 0:
        data = json.loads(stdout.decode())
        print("Vulnerabilities found.")
    else:
        print("Failed.")

asyncio.run(run_trivy())
