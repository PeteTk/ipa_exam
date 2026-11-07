import logging
import os
from ipaddress import IPv4Interface

import requests

from app.backends.planning import plan_interface as generic_plan_interface

logger = logging.getLogger(__name__)

# IOS-XE RESTCONF answers in XML (GET) or rejects the request with 415 (PUT)
# unless the YANG media types are requested explicitly.
RESTCONF_HEADERS = {
    "Accept": "application/yang-data+json",
    "Content-Type": "application/yang-data+json",
}


def _router_auth():
    user = os.environ.get("ROUTER_USER")
    password = os.environ.get("ROUTER_PASS")
    if not user or not password:
        raise PermissionError("ROUTER_USER / ROUTER_PASS are not set")
    return (user, password)


def get_interface_state(router, interface_name, http_get=None):
    """Return normalized interface status using RESTCONF."""
    url = f"https://{router}/restconf/data/ietf-interfaces:interfaces/interface={interface_name}"

    try:
        if http_get is not None:
            resp = http_get(url)
        else:
            resp = requests.get(
                url,
                auth=_router_auth(),
                headers=RESTCONF_HEADERS,
                verify=False,
                timeout=10,
            )

        if resp.status_code == 404:
            return {"status": "ok", "result": "not_found", "interface": None}
        if resp.status_code in (401, 403):
            return {"status": "error", "result": "authentication_failed"}
        if resp.status_code != 200:
            logger.warning("RESTCONF GET %s -> %s %s", url, resp.status_code,
                           getattr(resp, "text", "")[:300])
            return {"status": "error", "result": "backend_failed"}

        data = resp.json()["ietf-interfaces:interface"]
        name = data["name"]
        description = data.get("description")
        enabled = data.get("enabled", True)
        admin_state = "up" if enabled else "down"

        ipv4_str = None
        ipv4_data = data.get("ietf-ip:ipv4", {}).get("address", [])
        if ipv4_data:
            addr = ipv4_data[0]["ip"]
            mask = ipv4_data[0]["netmask"]
            ipv4_str = str(IPv4Interface(f"{addr}/{mask}"))

        return {
            "status": "ok",
            "result": "found",
            "interface": {
                "name": name,
                "ipv4": ipv4_str,
                "description": description,
                "admin_state": admin_state,
            },
        }
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except (ConnectionError, requests.exceptions.RequestException):
        return {"status": "error", "result": "connection_failed"}
    except Exception:
        return {"status": "error", "result": "backend_failed"}


def plan_interface(router, desired_interface, http_get=None):
    """Return create/update/no_change plan using RESTCONF status."""
    def _get_state(r, name):
        return get_interface_state(r, name, http_get=http_get)

    return generic_plan_interface(router, desired_interface, _get_state)


def apply_interface(router, desired_interface, http_put=None):
    """Apply complete desired interface state using RESTCONF."""
    try:
        number = int(desired_interface["name"].replace("Loopback", ""))
        url = f"https://{router}/restconf/data/Cisco-IOS-XE-native:native/interface/Loopback={number}"

        ipv4 = IPv4Interface(desired_interface["ipv4"])
        payload_loopback = {
            "name": number,
            "description": desired_interface["description"],
            "ip": {
                "address": {
                    "primary": {
                        "address": str(ipv4.ip),
                        "mask": str(ipv4.network.netmask),
                    }
                }
            },
        }
        if desired_interface.get("admin_state") == "down":
            payload_loopback["shutdown"] = [None]

        payload = {"Cisco-IOS-XE-native:Loopback": payload_loopback}

        if http_put is not None:
            resp = http_put(url, json=payload)
        else:
            resp = requests.put(
                url,
                json=payload,
                auth=_router_auth(),
                headers=RESTCONF_HEADERS,
                verify=False,
                timeout=10,
            )

        if resp.status_code in (200, 201, 204):
            return {"status": "ok", "result": "applied"}
        if resp.status_code in (401, 403):
            return {"status": "error", "result": "authentication_failed"}
        logger.warning("RESTCONF PUT %s -> %s %s", url, resp.status_code,
                       getattr(resp, "text", "")[:300])
        return {"status": "error", "result": "backend_failed"}
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except (ConnectionError, requests.exceptions.RequestException):
        return {"status": "error", "result": "connection_failed"}
    except Exception:
        return {"status": "error", "result": "backend_failed"}