def build_plan(desired_interface, current_interface):
    """
    Compare desired interface state with normalized current state
    and return a plan according to specs/plan-spec-v1.md.
    """
    managed_fields = ["ipv4", "description", "admin_state"]

    # กรณีที่ 1: Interface ยังไม่มีอยู่บน Router -> create
    if current_interface is None:
        changes = {
            field: {"to": desired_interface[field]}
            for field in managed_fields
            if field in desired_interface
        }
        return {
            "status": "ok",
            "result": "planned",
            "operation": "create",
            "changes": changes,
        }

    # กรณีที่ 2 & 3: เปรียบเทียบความแตกต่างของแต่ละฟิลด์
    changes = {}
    for field in managed_fields:
        desired_val = desired_interface.get(field)
        current_val = current_interface.get(field)
        
        if desired_val != current_val:
            changes[field] = {
                "from": current_val,
                "to": desired_val,
            }

    # มีฟิลด์ที่ต่างกันอย่างน้อย 1 ฟิลด์ -> update
    if changes:
        return {
            "status": "ok",
            "result": "planned",
            "operation": "update",
            "changes": changes,
        }

    # ค่าตรงกันหมดทุกฟิลด์ -> no_change
    return {
        "status": "ok",
        "result": "planned",
        "operation": "no_change",
        "changes": {},
    }