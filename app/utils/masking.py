def mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    local_masked = (local[:1] + "***") if local else "***"
    parts = domain.split(".")
    if not parts:
        return f"{local_masked}@***"
    domain_masked = (parts[0][:1] + "***") if parts[0] else "***"
    suffix = "." + ".".join(parts[1:]) if len(parts) > 1 else ""
    return f"{local_masked}@{domain_masked}{suffix}"


def safe_payload_preview(payload: str, limit: int = 18) -> str:
    if not payload:
        return ""
    if len(payload) <= limit:
        return payload
    return f"{payload[:limit]}..."
