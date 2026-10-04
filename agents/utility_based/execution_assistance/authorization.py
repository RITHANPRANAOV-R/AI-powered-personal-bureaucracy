from datetime import datetime, timezone

from .schema import ExecutionRequest


def validate_authorization(request: ExecutionRequest, step_id: str | None = None) -> str | None:
    authorization = request.execution_authorization
    if authorization is None:
        return "Execution authorization is required."
    if authorization.plan_id != request.plan_id:
        return "Execution authorization does not match the requested plan."
    if authorization.plan_version != request.plan_version:
        return "Execution authorization does not match the requested plan version."
    if authorization.session_id != request.workflow_plan.session_id:
        return "Execution authorization does not match the workflow session."
    if authorization.revoked:
        return "Execution authorization has been revoked."
    now = datetime.now(timezone.utc)
    if authorization.expires_at <= now:
        return "Execution authorization has expired."
    if authorization.approved_at > now:
        return "Execution authorization is not active yet."
    if step_id is not None and step_id not in authorization.approved_step_ids:
        return f"Execution step '{step_id}' is not authorized."
    return None


def authorization_contains_approval(authorization, approval_step_ids: set[str]) -> bool:
    return approval_step_ids.issubset(set(authorization.satisfied_approval_step_ids))