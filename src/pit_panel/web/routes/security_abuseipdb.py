"""AbuseIPDB routes — IP reputation check, blacklist browsing."""

import html
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_admin

router = APIRouter()


async def _abuseipdb_check(ip: str, api_key: str) -> dict[str, Any]:
    import http.client
    import json

    try:
        ip = ip.replace("\r", "").replace("\n", "")
        api_key = api_key.replace("\r", "").replace("\n", "")
        conn = http.client.HTTPSConnection("api.abuseipdb.com", timeout=10)
        headers = {"Key": api_key, "Accept": "application/json"}
        conn.request("GET", f"/api/v2/check?ipAddress={ip}&maxAgeInDays=90", headers=headers)
        resp = conn.getresponse()
        if resp.status == 200:
            data = json.loads(resp.read().decode())
            score = data.get("data", {}).get("abuseConfidenceScore", 0)
            return {
                "ip": ip,
                "score": score,
                "reports": data.get("data", {}).get("totalReports", 0),
            }
        return {"ip": ip, "error": f"HTTP {resp.status}"}
    except Exception as e:
        return {"ip": ip, "error": str(e)}


async def _abuseipdb_blacklist(api_key: str, limit: int = 20) -> list[dict[str, Any]]:
    import http.client
    import json

    try:
        api_key = api_key.replace("\r", "").replace("\n", "")
        conn = http.client.HTTPSConnection("api.abuseipdb.com", timeout=15)
        headers = {"Key": api_key, "Accept": "application/json"}
        conn.request(
            "GET",
            f"/api/v2/blacklist?confidenceMinimum=90&limit={limit}",
            headers=headers,
        )
        resp = conn.getresponse()
        if resp.status == 200:
            data = json.loads(resp.read().decode())
            entries = data.get("data", [])
            return [
                {
                    "ip": e.get("ipAddress", ""),
                    "score": e.get("abuseConfidenceScore", 0),
                    "reports": e.get("totalReports", 0),
                    "last": e.get("lastReportedAt", ""),
                }
                for e in entries
            ]
        return []
    except Exception:
        return []


@router.get("/security/abuseipdb-blacklist", response_class=HTMLResponse)
async def security_abuseipdb_blacklist(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    settings = get_settings()
    api_key = getattr(settings, "abuseipdb_api_key", "")

    if not api_key:
        return HTMLResponse(
            '<div class="text-red-500 text-sm">No AbuseIPDB API key configured.</div>'
        )

    blacklist = await _abuseipdb_blacklist(api_key)

    if not blacklist:
        return HTMLResponse('<div class="text-sm text-gray-500">No blacklist entries found.</div>')

    output = '<div class="space-y-2">'
    for entry in blacklist:
        score = entry["score"]
        color_class = "text-red-500" if score > 80 else "text-orange-500"
        safe_ip = html.escape(str(entry["ip"]))
        safe_score = html.escape(str(score))
        safe_reports = html.escape(str(entry["reports"]))
        output += f"""
        <div class="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-800 rounded">
            <span class="font-mono text-sm">{safe_ip}</span>
            <div class="text-xs text-gray-500">
                Score: <span class="{color_class} font-bold">{safe_score}</span> |
                Reports: {safe_reports}
            </div>
        </div>
        """
    output += "</div>"

    return HTMLResponse(output)


@router.post("/security/abuseipdb-check", response_class=HTMLResponse)
async def security_abuseipdb_check(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    form = await request.form()
    ip = form.get("ip")
    api_key = form.get("api_key")

    if not ip or not api_key:
        return HTMLResponse('<div class="text-red-500 text-sm">IP and API key are required.</div>')

    result = await _abuseipdb_check(ip, api_key)

    if "error" in result:
        err_msg = html.escape(str(result["error"]))
        return HTMLResponse(f'<div class="text-red-500 text-sm">Error: {err_msg}</div>')

    score = result.get("score", 0)
    color_class = (
        "text-green-500" if score < 20 else ("text-orange-500" if score < 80 else "text-red-500")
    )

    safe_ip = html.escape(str(result["ip"]))

    return HTMLResponse(f'''
    <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded border border-gray-200
                dark:border-gray-700">
        <div class="flex justify-between items-center">
            <span class="font-mono">{safe_ip}</span>
            <span class="{color_class} font-bold">Score: {score}/100</span>
        </div>
        <div class="text-xs text-gray-500 mt-1">Total Reports: {result.get("reports", 0)}</div>
    </div>
    ''')
