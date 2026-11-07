from pathlib import Path
import yaml

ALLOWED_ROUTERS = {
    "10.0.29.101",
    "10.0.29.102",
    "10.0.29.103",
    "10.0.29.104",
    "10.0.29.105",
}

ALLOWED_METHODS = {
    "restconf": {"status", "plan", "apply"},
    "netconf": {"status", "plan", "apply"},
    "ansible": {"apply"},
    "netmiko-textfsm": {"status", "delete"},
}


def validate_request(data):
    """
    Validate one IPA2026 desired-state request dictionary.
    """
    if not isinstance(data, dict):
        return {"status": "error", "result": "invalid_yaml"}

    # 1. Version validation (Must be exact integer 1, exclude bool)
    if "version" not in data:
        return {"status": "error", "result": "invalid_version"}
    version = data["version"]
    if type(version) is not int or version != 1:
        return {"status": "error", "result": "invalid_version"}

    # 2. Router validation
    if "router" not in data:
        return {"status": "error", "result": "missing_router"}
    if data["router"] not in ALLOWED_ROUTERS:
        return {"status": "error", "result": "invalid_router"}

    # 3. Method validation
    if "method" not in data:
        return {"status": "error", "result": "missing_method"}
    method = data["method"]
    if method not in ALLOWED_METHODS:
        return {"status": "error", "result": "invalid_method"}

    # 4. Action validation
    if "action" not in data:
        return {"status": "error", "result": "missing_action"}
    action = data["action"]
    if action not in ALLOWED_METHODS[method]:
        return {"status": "error", "result": "invalid_action"}

    # 5. Desired interface structure validation
    if "desired" not in data or not isinstance(data["desired"], dict):
        return {"status": "error", "result": "missing_desired"}

    desired = data["desired"]
    if "interface" not in desired or not isinstance(desired["interface"], dict):
        return {"status": "error", "result": "missing_interface"}

    interface = desired["interface"]
    if "name" not in interface or not interface["name"]:
        return {"status": "error", "result": "missing_interface_name"}

    # 6. Action-specific validation for 'plan' and 'apply'
    if action in ("plan", "apply"):
        if "ipv4" not in interface:
            return {"status": "error", "result": "missing_ipv4"}
        if "description" not in interface:
            return {"status": "error", "result": "missing_description"}
        if "admin_state" not in interface:
            return {"status": "error", "result": "missing_admin_state"}
        if interface["admin_state"] not in ("up", "down"):
            return {"status": "error", "result": "invalid_admin_state"}

    return {"status": "ok", "result": "accepted"}


def process_request_file(path):
    """
    Read a YAML request file, validate it, and return a response dictionary.
    """
    filepath = Path(path)
    if not filepath.exists():
        return {"status": "error", "result": "invalid_yaml"}

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return {"status": "error", "result": "invalid_yaml"}

    return validate_request(data)