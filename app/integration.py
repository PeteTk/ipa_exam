from pathlib import Path
import yaml

from app.core import validate_request
from app.dispatcher import dispatch_request
from app.request_handler import validate_webex_envelope


def process_request(mentioned_people, attachment_path, bot_person_id):
    """
    Validate envelope, parse & validate YAML, then dispatch to router.
    """
    # 1. Validate Webex Mention & Attachment envelope
    envelope_error = validate_webex_envelope(
        mentioned_people, attachment_path, bot_person_id
    )
    if envelope_error is not None:
        return envelope_error

    # 2. Read and parse YAML file
    try:
        with open(attachment_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return {"status": "error", "result": "invalid_yaml"}

    # 3. Validate request schema
    try:
        validation_res = validate_request(data)
    except Exception:
        return {"status": "error", "result": "invalid_yaml"}
    if validation_res.get("status") == "error":
        return validation_res

    # 4. Dispatch to backend (always reply, even on unexpected failure)
    try:
        return dispatch_request(data)
    except Exception:
        return {"status": "error", "result": "backend_failed"}