"""IP blocklist management: sources, fetching, daily import."""

import asyncio
import time

import httpx

from pit_panel.config import get_settings
from pit_panel.db.session import get_sessionmaker
from pit_panel.security.ipban import ban_ips_bulk

BLOCKLIST_SOURCES = {
    "firehol_level1": {
        "name": "FireHOL Level 1",
        "url": "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master/firehol_level1.netset",
        "desc": "Known attackers, malware C&C",
    },
    "firehol_level2": {
        "name": "FireHOL Level 2",
        "url": "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master/firehol_level2.netset",
        "desc": "Unsolicited traffic, P2P attacks",
    },
    "firehol_level3": {
        "name": "FireHOL Level 3",
        "url": "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master/firehol_level3.netset",
        "desc": "Botnets, command & control",
    },
    "firehol_webserver": {
        "name": "FireHOL Web Attacks",
        "url": "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master/firehol_webserver.netset",
        "desc": "IPs attacking web servers",
    },
    "spamhaus_drop": {
        "name": "Spamhaus DROP",
        "url": "https://www.spamhaus.org/drop/drop.txt",
        "desc": "Spamhaus Don't Route Or Peer list",
    },
    "spamhaus_edrop": {
        "name": "Spamhaus EDROP",
        "url": "https://www.spamhaus.org/drop/edrop.txt",
        "desc": "Spamhaus Extended DROP",
    },
    "blocklist_de_ssh": {
        "name": "Blocklist.de SSH",
        "url": "https://lists.blocklist.de/lists/ssh.txt",
        "desc": "SSH brute-force attackers",
    },
    "blocklist_de_ftp": {
        "name": "Blocklist.de FTP",
        "url": "https://lists.blocklist.de/lists/ftp.txt",
        "desc": "FTP brute-force attackers",
    },
}


_BLOCKLIST_CACHE: dict[str, tuple[list[str], float]] = {}
CACHE_TTL = 3600  # 1 hour


async def fetch_blocklist(url: str) -> list[str]:
    now = time.time()
    if url in _BLOCKLIST_CACHE:
        cached_ips, timestamp = _BLOCKLIST_CACHE[url]
        if now - timestamp < CACHE_TTL:
            return cached_ips

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []
            ips = []
            for line in resp.text.split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    ips.append(line.split()[0] if " " in line else line)
            result = ips[:200]
            _BLOCKLIST_CACHE[url] = (result, now)
            return result
    except Exception:
        return []


async def daily_blocklist_import():
    while True:
        await asyncio.sleep(86400)
        settings = get_settings()
        if not getattr(settings, "auto_blocklist", True):
            continue
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as db:
            for key, info in BLOCKLIST_SOURCES.items():
                try:
                    ips = await fetch_blocklist(info["url"])
                    await ban_ips_bulk(db, ips, f"auto:{key}", 10080)
                except Exception:
                    pass
