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
    router = data.get("router")
    if not router:
        return {"status": "error", "result": "missing_router"}
    if not isinstance(router, str) or router not in ALLOWED_ROUTERS:
        return {"status": "error", "result": "invalid_router"}

    # 3. Method validation
    method = data.get("method")
    if not method:
        return {"status": "error", "result": "missing_method"}
    if not isinstance(method, str) or method not in ALLOWED_METHODS:
        return {"status": "error", "result": "invalid_method"}

    # 4. Action validation
    action = data.get("action")
    if not action:
        return {"status": "error", "result": "missing_action"}
    if not isinstance(action, str) or action not in ALLOWED_METHODS[method]:
        return {"status": "error", "result": "invalid_action"}

    # 5. Desired interface structure validation
    if "desired" not in data or not isinstance(data["desired"], dict):
        return {"status": "error", "result": "missing_desired"}

    desired = data["desired"]
    if "interface" not in desired or not isinstance(desired["interface"], dict):
        return {"status": "error", "result": "missing_interface"}

    interface = desired["interface"]
    name = interface.get("name")
    if not isinstance(name, str) or not name.strip():
        return {"status": "error", "result": "missing_interface_name"}

    # 6. Action-specific validation for 'plan' and 'apply'
    if action in ("plan", "apply"):
        ipv4 = interface.get("ipv4")
        if not isinstance(ipv4, str) or not ipv4.strip():
            return {"status": "error", "result": "missing_ipv4"}
        description = interface.get("description")
        if not isinstance(description, str) or not description.strip():
            return {"status": "error", "result": "missing_description"}
        admin_state = interface.get("admin_state")
        if admin_state is None or admin_state == "":
            return {"status": "error", "result": "missing_admin_state"}
        if admin_state not in ("up", "down"):
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