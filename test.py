import asyncio
from pit_panel.core.docker_ops import DockerManager

async def main():
    manager = DockerManager()
    containers = await manager.ps_all()
    print("Total containers:", len(containers))
    running = sum(1 for c in containers if c.get("State") == "running")
    print("Running containers:", running)

if __name__ == "__main__":
    asyncio.run(main())
