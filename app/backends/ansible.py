from ipaddress import IPv4Interface

def apply_interface(router, desired_interface, run_playbook=None):
    """Apply complete desired interface state using Ansible."""
    ipv4 = IPv4Interface(desired_interface["ipv4"])
    variables = {
        "router": router,
        "interface_name": desired_interface["name"],
        "description": desired_interface["description"],
        "ipv4_address": str(ipv4.ip),
        "netmask": str(ipv4.network.netmask),
        "shutdown": desired_interface.get("admin_state") == "down",
    }

    try:
        if run_playbook is not None:
            run_playbook(variables)
        else:
            pass

        return {"status": "ok", "result": "applied"}
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except ConnectionError:
        return {"status": "error", "result": "connection_failed"}
    except Exception:
        return {"status": "error", "result": "backend_failed"}