import json
import logging
import os
import subprocess
import sys
from ipaddress import IPv4Interface
from pathlib import Path

logger = logging.getLogger(__name__)

PLAYBOOK = Path(__file__).resolve().parents[2] / "ansible" / "apply_interface.yml"
PLAYBOOK_TIMEOUT = 90

AUTH_MARKERS = (
    "authentication failed",
    "invalid/incorrect password",
    "permission denied",
)


def _ansible_playbook_cmd():
    candidate = Path(sys.executable).parent / "ansible-playbook"
    return str(candidate) if candidate.exists() else "ansible-playbook"


def _run_playbook(variables):
    """Run the apply playbook; map failures to built-in exceptions."""
    if not os.environ.get("ROUTER_USER") or not os.environ.get("ROUTER_PASS"):
        raise PermissionError("ROUTER_USER / ROUTER_PASS are not set")

    env = dict(os.environ, ANSIBLE_HOST_KEY_CHECKING="False",
               ANSIBLE_NOCOLOR="1")
    cmd = [
        _ansible_playbook_cmd(),
        "-i", f"{variables['router']},",
        str(PLAYBOOK),
        "-e", json.dumps(variables),
    ]
    try:
        proc = subprocess.run(
            cmd, env=env, capture_output=True, text=True,
            timeout=PLAYBOOK_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConnectionError("ansible-playbook timed out") from exc

    if proc.returncode == 0:
        return
    output = (proc.stdout + proc.stderr).lower()
    logger.warning("ansible-playbook rc=%s\n%s", proc.returncode,
                   (proc.stdout + proc.stderr)[-1500:])
    if any(marker in output for marker in AUTH_MARKERS):
        raise PermissionError("router rejected credentials")
    if proc.returncode == 4 or "unreachable" in output:
        raise ConnectionError("router unreachable")
    raise RuntimeError(f"ansible-playbook failed (rc={proc.returncode})")


def apply_interface(router, desired_interface, run_playbook=None):
    """Apply complete desired interface state using Ansible."""
    try:
        ipv4 = IPv4Interface(desired_interface["ipv4"])
        variables = {
            "router": router,
            "interface_name": desired_interface["name"],
            "description": desired_interface["description"],
            "ipv4_address": str(ipv4.ip),
            "netmask": str(ipv4.network.netmask),
            "shutdown": desired_interface.get("admin_state") == "down",
        }

        if run_playbook is None:
            run_playbook = _run_playbook
        run_playbook(variables)

        return {"status": "ok", "result": "applied"}
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except (ConnectionError, TimeoutError, subprocess.TimeoutExpired):
        return {"status": "error", "result": "connection_failed"}
    except Exception:
        logger.exception("Ansible backend failed")
        return {"status": "error", "result": "backend_failed"}