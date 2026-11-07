import logging
import os
import xml.etree.ElementTree as ET
from ipaddress import IPv4Interface

from app.backends.planning import plan_interface as generic_plan_interface

logger = logging.getLogger(__name__)


def _open_session(router):
    """Open an ncclient session, mapping library errors to built-ins."""
    # Lazy import: keeps the module importable without touching a router.
    from ncclient import manager
    from ncclient.operations.errors import TimeoutExpiredError
    from ncclient.transport.errors import AuthenticationError, TransportError

    user = os.environ.get("ROUTER_USER")
    password = os.environ.get("ROUTER_PASS")
    if not user or not password:
        raise PermissionError("ROUTER_USER / ROUTER_PASS are not set")

    try:
        return manager.connect(
            host=router,
            port=830,
            username=user,
            password=password,
            hostkey_verify=False,
            allow_agent=False,
            look_for_keys=False,
            device_params={"name": "iosxe"},
            timeout=15,
        )
    except AuthenticationError as exc:
        raise PermissionError(str(exc)) from exc
    except (TransportError, TimeoutExpiredError, OSError, EOFError) as exc:
        raise ConnectionError(str(exc)) from exc


def _netconf_get_config(router, filter_xml):
    from ncclient.operations.rpc import RPCError

    session = _open_session(router)
    try:
        reply = session.get_config(source="running", filter=("subtree", filter_xml))
        return reply.xml
    except RPCError as exc:
        raise RuntimeError(str(exc)) from exc
    finally:
        session.close_session()


def _netconf_edit_config(router, config_xml):
    from ncclient.operations.rpc import RPCError

    session = _open_session(router)
    try:
        session.edit_config(target="running", config=config_xml)
    except RPCError as exc:
        raise RuntimeError(str(exc)) from exc
    finally:
        session.close_session()


def get_interface_state(router, interface_name, netconf_get_config=None):
    """Return normalized interface status using NETCONF."""
    filter_xml = f"""<interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces">
  <interface>
    <name>{interface_name}</name>
  </interface>
</interfaces>"""

    try:
        if netconf_get_config is None:
            netconf_get_config = _netconf_get_config
        xml_data = netconf_get_config(router, filter_xml)

        root = ET.fromstring(xml_data)
        ns = {
            "if": "urn:ietf:params:xml:ns:yang:ietf-interfaces",
            "ip": "urn:ietf:params:xml:ns:yang:ietf-ip",
        }
        iface = root.find(".//if:interface", ns)
        if iface is None:
            return {"status": "ok", "result": "not_found", "interface": None}

        name_elem = iface.find("if:name", ns)
        name = name_elem.text if name_elem is not None else interface_name

        desc_elem = iface.find("if:description", ns)
        description = desc_elem.text if desc_elem is not None else None

        enabled_elem = iface.find("if:enabled", ns)
        enabled = (enabled_elem.text.lower() == "true") if enabled_elem is not None else True
        admin_state = "up" if enabled else "down"

        ip_elem = iface.find(".//ip:address/ip:ip", ns)
        mask_elem = iface.find(".//ip:address/ip:netmask", ns)
        ipv4_str = None
        if ip_elem is not None and mask_elem is not None:
            ipv4_str = str(IPv4Interface(f"{ip_elem.text}/{mask_elem.text}"))

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
    except ConnectionError:
        return {"status": "error", "result": "connection_failed"}
    except Exception:
        logger.exception("NETCONF backend failed")
        return {"status": "error", "result": "backend_failed"}


def plan_interface(router, desired_interface, netconf_get_config=None):
    """Return create/update/no_change plan using NETCONF status."""
    def _get_state(r, name):
        return get_interface_state(r, name, netconf_get_config=netconf_get_config)

    return generic_plan_interface(router, desired_interface, _get_state)


def apply_interface(router, desired_interface, netconf_edit_config=None):
    """Apply complete desired interface state using NETCONF."""
    number = int(desired_interface["name"].replace("Loopback", ""))
    ipv4 = IPv4Interface(desired_interface["ipv4"])
    shutdown_tag = "<shutdown/>" if desired_interface.get("admin_state") == "down" else ""

    config_xml = f"""<config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
  <native xmlns="http://cisco.com/ns/yang/Cisco-IOS-XE-native">
    <interface>
      <Loopback nc:operation="replace">
        <name>{number}</name>
        <description>{desired_interface["description"]}</description>
        <ip>
          <address>
            <primary>
              <address>{ipv4.ip}</address>
              <mask>{ipv4.network.netmask}</mask>
            </primary>
          </address>
        </ip>
        {shutdown_tag}
      </Loopback>
    </interface>
  </native>
</config>"""

    try:
        if netconf_edit_config is None:
            netconf_edit_config = _netconf_edit_config
        netconf_edit_config(router, config_xml)
        return {"status": "ok", "result": "applied"}
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except ConnectionError:
        return {"status": "error", "result": "connection_failed"}
    except Exception:
        logger.exception("NETCONF backend failed")
        return {"status": "error", "result": "backend_failed"}