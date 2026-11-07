from app.planner import build_plan

def plan_interface(router, desired_interface, get_interface_state):
    """
    Build a Part 2 plan from backend status.
    """
    interface_name = desired_interface["name"]
    status_res = get_interface_state(router, interface_name)

    # 1. หากเกิด Error ในระดับ Backend ให้ส่ง Error นั้นกลับทันที
    if status_res.get("status") == "error":
        return status_res

    # 2. แปลงผลลัพธ์เป็น current_interface เพื่อส่งให้ build_plan
    if status_res.get("result") == "found":
        current_interface = status_res.get("interface")
    else:
        current_interface = None

    return build_plan(desired_interface, current_interface)