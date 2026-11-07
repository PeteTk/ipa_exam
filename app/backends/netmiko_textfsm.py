import logging
import os

logger = logging.getLogger(__name__)


def _connect(router):
    """Open a Netmiko SSH session, mapping library errors to built-ins."""
    # Imported lazily so the module (and the public tests) load without
    # a router or SSH stack being touched.
    from netmiko import ConnectHandler
    from netmiko.exceptions import (
        NetmikoAuthenticationException,
        NetmikoTimeoutException,
    )

    user = os.environ.get("ROUTER_USER")
    password = os.environ.get("ROUTER_PASS")
    if not user or not password:
        raise PermissionError("ROUTER_USER / ROUTER_PASS are not set")

    try:
        return ConnectHandler(
            device_type="cisco_ios",
            host=router,
            username=user,
            password=password,
            conn_timeout=10,
            auth_timeout=10,
            banner_timeout=10,
        )
    except NetmikoAuthenticationException as exc:
        raise PermissionError(str(exc)) from exc
    except (NetmikoTimeoutException, OSError, EOFError) as exc:
        raise ConnectionError(str(exc)) from exc


def _is_cli_error(output):
    """True when IOS rejected the command (e.g. the interface does not exist)."""
    text = output.strip() if isinstance(output, str) else ""
    return text.startswith("%") or "Invalid input" in text or "^" in text


def _read_state(conn, interface_name):
    """Return (ip_info, descriptions) parsed by TextFSM; [] when absent."""
    command = f"show ip interface {interface_name}"
    # Look at the raw output first: IOS answers a missing interface with
    # "% Invalid input detected at '^' marker", and the TextFSM template
    # raises a State Error on that text instead of returning an empty list.
    if _is_cli_error(conn.send_command(command)):
        return [], []
    ip_info = conn.send_command(command, use_textfsm=True)
    if not isinstance(ip_info, list):
        return [], []
    descriptions = conn.send_command(
        f"show interfaces {interface_name} description", use_textfsm=True
    )
    if not isinstance(descriptions, list):
        descriptions = []
    return ip_info, descriptions


def _netmiko_get(router, interface_name):
    conn = _connect(router)
    try:
        return _read_state(conn, interface_name)
    finally:
        conn.disconnect()


def _netmiko_delete(router, interface_name):
    """Delete the interface; return "deleted" or "not_found"."""
    conn = _connect(router)
    try:
        ip_info, _ = _read_state(conn, interface_name)
        if not ip_info:
            return "not_found"
        conn.send_config_set([f"no interface {interface_name}"])
        ip_info, _ = _read_state(conn, interface_name)
        if ip_info:
            raise RuntimeError(f"{interface_name} still present after delete")
        return "deleted"
    finally:
        conn.disconnect()


def get_interface_state(router, interface_name, netmiko_get=None):
    """Return normalized interface status using Netmiko + TextFSM."""
    try:
        if netmiko_get is None:
            netmiko_get = _netmiko_get
        ip_info, descriptions = netmiko_get(router, interface_name)

        if not ip_info:
            return {"status": "ok", "result": "not_found", "interface": None}

        info = ip_info[0]
        link_status = info.get("link_status", "").lower()
        admin_state = "down" if "administratively down" in link_status else "up"

        ip_addr = info.get("ip_address", [None])[0]
        prefix_len = info.get("prefix_length", [None])[0]
        ipv4_str = f"{ip_addr}/{prefix_len}" if ip_addr and prefix_len else None

        desc = None
        for d in descriptions:
            port = d.get("port", "")
            # แปลงชื่อย่อ Lo123 ให้กลายเป็น Loopback123
            normalized_port = port.replace("Lo", "Loopback") if port.startswith("Lo") else port
            if normalized_port == interface_name:
                desc = d.get("description")
                break

        return {
            "status": "ok",
            "result": "found",
            "interface": {
                "name": interface_name,
                "ipv4": ipv4_str,
                "description": desc,
                "admin_state": admin_state,
            },
        }
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except ConnectionError:
        return {"status": "error", "result": "connection_failed"}
    except Exception:
        logger.exception("Netmiko backend failed")
        return {"status": "error", "result": "backend_failed"}


def delete_interface(router, interface_name, netmiko_delete=None):
    """Delete an interface using Netmiko."""
    try:
        if netmiko_delete is None:
            netmiko_delete = _netmiko_delete
        res = netmiko_delete(router, interface_name)
        if res == "not_found":
            return {"status": "ok", "result": "not_found", "interface": None}
        return {"status": "ok", "result": "deleted"}
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except ConnectionError:
        return {"status": "error", "result": "connection_failed"}
    except Exception:
        logger.exception("Netmiko backend failed")
        return {"status": "error", "result": "backend_failed"}