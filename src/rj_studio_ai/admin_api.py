"""Single-business operational API: explicit credentials, permissions and resource scope."""

import hashlib
import hmac
import json
import re

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from rj_studio_ai.automation_operations import OperationConflict
from rj_studio_ai.persistence import PersistenceUnavailable


def admin_router(settings, store):
    router = APIRouter(prefix="/admin/conversations")

    def authorize(request, opaque_id, permission):
        digest = settings.operator_secret_sha256
        scopes = settings.operator_conversations
        if (
            not re.fullmatch("[a-f0-9]{64}", digest)
            or not re.fullmatch("[a-zA-Z0-9_-]{1,64}", settings.operator_id)
            or not settings.operator_permissions
            or any(p not in ("read", "control") for p in settings.operator_permissions)
            or not scopes
            or any(s != "*" and not re.fullmatch("[a-f0-9]{32}", s) for s in scopes)
        ):
            raise HTTPException(503, "operator_configuration_unavailable")
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        if (
            len(token) < 32
            or len(token) > 512
            or not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), digest)
        ):
            raise HTTPException(
                401, "authentication_required", headers={"WWW-Authenticate": "Bearer"}
            )
        if permission not in settings.operator_permissions or (
            "*" not in scopes and opaque_id not in scopes
        ):
            raise HTTPException(403, "operation_forbidden")
        if not re.fullmatch("[a-f0-9]{32}", opaque_id):
            raise HTTPException(404, "conversation_not_found")

    @router.get("/{opaque_id}/automation")
    def inspect(opaque_id: str, request: Request):
        authorize(request, opaque_id, "read")
        try:
            return store.get_automation_state(opaque_id)
        except LookupError:
            raise HTTPException(404, "conversation_not_found") from None
        except PersistenceUnavailable:
            raise HTTPException(503, "persistence_unavailable") from None

    @router.post("/{opaque_id}/automation/{action}")
    async def change(opaque_id: str, action: str, request: Request):
        authorize(request, opaque_id, "control")
        if action not in ("pause", "resume"):
            raise HTTPException(404, "operation_not_found")
        try:
            # Bound input before parsing; never echo Pydantic validation inputs.
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 1024:
                    raise HTTPException(413, "request_too_large")
            payload = json.loads(body)
            if not isinstance(payload, dict) or set(payload) != {
                "operation_id",
                "expected_revision",
            }:
                raise ValueError("invalid_operation")
            if not isinstance(payload["operation_id"], str):
                raise ValueError("invalid_operation")
            return await run_in_threadpool(
                store.change_automation,
                opaque_id,
                action,
                payload["operation_id"],
                payload["expected_revision"],
                settings.operator_id,
            )
        except OperationConflict as error:
            raise HTTPException(409, str(error)) from None
        except (ValueError, TypeError):
            raise HTTPException(422, "invalid_operation") from None
        except LookupError:
            raise HTTPException(404, "conversation_not_found") from None
        except PersistenceUnavailable:
            raise HTTPException(503, "persistence_unavailable") from None

    return router
