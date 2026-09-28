import json
import urllib.request
from typing import List, Dict, Any
from src.database import get_db, log_audit

def dispatch_webhook(event_type: str, payload: Dict[str, Any]):
    """
    Dispatches outbound webhook payloads asynchronously or logs them
    for Discord/Slack integrations.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Store in audit logs
    log_audit("WEBHOOK_DISPATCHED", "system", event_type, json.dumps(payload)[:100])
    
    # In offline environment, we capture webhook events in audit trail
    conn.close()
    return True
