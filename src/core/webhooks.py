import json
import os
import threading
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from src.database import get_db, log_audit

def _send_http_request(url: str, payload_bytes: bytes, content_type: str = "application/json"):
    """Performs HTTP POST in a worker thread so request handler is never blocked."""
    try:
        req = urllib.request.Request(
            url,
            data=payload_bytes,
            headers={
                "Content-Type": content_type,
                "User-Agent": "Veritas-Hackathon-Engine/2.0 (+https://github.com/veeralsaxena/Dogfood)"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            status = response.getcode()
            log_audit("WEBHOOK_DELIVERED", "system", url[:60], f"Status: {status}")
    except urllib.error.HTTPError as e:
        log_audit("WEBHOOK_HTTP_ERROR", "system", url[:60], f"Code: {e.code}, Reason: {e.reason}")
    except Exception as e:
        log_audit("WEBHOOK_OFFLINE", "system", url[:60], f"Offline/unreachable: {str(e)[:100]}")

def build_discord_payload(event_type: str, payload: Dict[str, Any]) -> dict:
    """Formats structured Discord embeds for rich notification delivery."""
    now_iso = datetime.now(timezone.utc).isoformat()
    
    color_map = {
        "project.submitted": 0x10B981,   # Emerald
        "team.created": 0x3B82F6,        # Blue
        "team.joined": 0x38BDF8,         # Light Blue
        "score.submitted": 0x8B5CF6,     # Purple
        "results.published": 0xF59E0B,   # Amber/Gold
        "test.ping": 0x00E5D0,           # Teal
    }
    color = color_map.get(event_type, 0x10B981)

    fields = []
    title = f"Veritas Platform Event: {event_type}"
    desc = payload.get("summary") or payload.get("message") or ""

    if event_type == "project.submitted":
        title = f"New Project Submitted: {payload.get('title', 'Untitled')}"
        if payload.get("team_name"):
            fields.append({"name": "Team", "value": str(payload.get("team_name")), "inline": True})
        if payload.get("track_name"):
            fields.append({"name": "Track", "value": str(payload.get("track_name")), "inline": True})
        if payload.get("repo_url"):
            fields.append({"name": "Repository", "value": str(payload.get("repo_url")), "inline": False})
        if payload.get("demo_url"):
            fields.append({"name": "Live Demo", "value": str(payload.get("demo_url")), "inline": True})
            
    elif event_type == "team.created":
        title = f"Team Registered: {payload.get('team_name', 'Unnamed Team')}"
        fields.append({"name": "Captain", "value": str(payload.get("creator_email", "N/A")), "inline": True})
        fields.append({"name": "Invite Code", "value": f"`{payload.get('invite_code', 'N/A')}`", "inline": True})
        if payload.get("event_name"):
            fields.append({"name": "Competition", "value": str(payload.get("event_name")), "inline": False})

    elif event_type == "team.joined":
        title = f"Member Joined Team: {payload.get('team_name', 'Team')}"
        fields.append({"name": "New Member", "value": str(payload.get("member_email", "N/A")), "inline": True})
        fields.append({"name": "Roster Size", "value": f"{payload.get('roster_count', 1)} / 4 members", "inline": True})

    elif event_type == "score.submitted":
        title = f"Evaluation Recorded: {payload.get('project_title', 'Project')}"
        fields.append({"name": "Track", "value": str(payload.get("track_name", "General")), "inline": True})
        fields.append({"name": "Evaluator", "value": "Panel Judge (Sealed)", "inline": True})

    elif event_type == "results.published":
        title = "Official Results Published & Cryptographically Signed"
        desc = "The organizer has certified the final standings with an RFC 8032 Ed25519 signature."
        fields.append({"name": "Projects Ranked", "value": str(payload.get("project_count", "All")), "inline": True})
        fields.append({"name": "Signature Preview", "value": f"`{str(payload.get('signature_preview', 'VALID'))}`", "inline": True})

    elif event_type == "test.ping":
        title = "Veritas Discord Integration Active"
        desc = "Your Discord webhook is successfully connected to the Veritas competitive evaluation engine!"
        fields.append({"name": "Delivery Status", "value": "200 OK — Ready for live event updates", "inline": True})
        fields.append({"name": "Triggered By", "value": str(payload.get("sender", "Organizer")), "inline": True})

    embed = {
        "title": title,
        "description": desc[:2000] if desc else None,
        "color": color,
        "fields": fields,
        "footer": {
            "text": "Veritas Hackathon Engine · 100% Offline & Open Source"
        },
        "timestamp": now_iso
    }

    return {
        "username": "Veritas Engine",
        "avatar_url": "https://raw.githubusercontent.com/veeralsaxena/Dogfood/main/spec/favicon.png",
        "embeds": [embed]
    }

def dispatch_webhook(event_type: str, payload: Dict[str, Any], endpoint_url: Optional[str] = None, event_id: Optional[str] = None) -> bool:
    """
    Dispatches outbound webhook payloads asynchronously to Discord, Slack, or generic HTTP endpoints.
    In offline environments, cleanly catches network failures and logs to SQLite audit log without throwing errors.
    """
    # 1. Store in audit log first
    log_audit("WEBHOOK_DISPATCHED", "system", event_type, json.dumps(payload)[:200])

    # 2. Determine target URL
    target_url = endpoint_url
    if not target_url and event_id:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT webhook_url FROM events WHERE id = ?", (event_id,))
        row = cursor.fetchone()
        if row and row["webhook_url"]:
            target_url = row["webhook_url"].strip()
        conn.close()

    if not target_url:
        target_url = os.environ.get("DISCORD_WEBHOOK_URL")
        if not target_url:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT webhook_url FROM events WHERE webhook_url IS NOT NULL AND webhook_url != '' LIMIT 1")
            row = cursor.fetchone()
            if row and row["webhook_url"]:
                target_url = row["webhook_url"].strip()
            conn.close()

    if not target_url:
        return True  # No webhook configured; logged to audit, success

    # 3. Format payload for Discord or generic HTTP
    if "discord.com/api/webhooks" in target_url:
        body_dict = build_discord_payload(event_type, payload)
    else:
        body_dict = {
            "event": event_type,
            "data": payload,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    payload_bytes = json.dumps(body_dict).encode("utf-8")

    # 4. Dispatch in non-blocking daemon thread so web worker is NEVER blocked
    thread = threading.Thread(target=_send_http_request, args=(target_url, payload_bytes), daemon=True)
    thread.start()
    return True
