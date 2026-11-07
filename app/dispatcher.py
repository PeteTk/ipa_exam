from app.backends import ansible, netconf, netmiko_textfsm, restconf


def dispatch_request(data):
    """
    Dispatch a validated request to the appropriate backend adapter.
    """
    method = data["method"]
    action = data["action"]
    router = data["router"]
    desired_interface = data["desired"]["interface"]
    interface_name = desired_interface["name"]

    # 1. RESTCONF Backend
    if method == "restconf":
        if action == "status":
            return restconf.get_interface_state(router, interface_name)
        elif action == "plan":
            return restconf.plan_interface(router, desired_interface)
        elif action == "apply":
            return restconf.apply_interface(router, desired_interface)

    # 2. NETCONF Backend
    elif method == "netconf":
        if action == "status":
            return netconf.get_interface_state(router, interface_name)
        elif action == "plan":
            return netconf.plan_interface(router, desired_interface)
        elif action == "apply":
            return netconf.apply_interface(router, desired_interface)

    # 3. Ansible Backend
    elif method == "ansible":
        if action == "apply":
            return ansible.apply_interface(router, desired_interface)

    # 4. Netmiko + TextFSM Backend
    elif method == "netmiko-textfsm":
        if action == "status":
            return netmiko_textfsm.get_interface_state(router, interface_name)
        elif action == "delete":
            return netmiko_textfsm.delete_interface(router, interface_name)

    return {"status": "error", "result": "invalid_action"}