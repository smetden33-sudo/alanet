from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, HTTPException


app = FastAPI(title="ALANET staging Remnawave mock")

users_by_username: dict[str, dict] = {}
users_by_id: dict[int, dict] = {}
next_user_id = 100000

STAGING_NODE_UUID = "00000000-0000-4000-8000-000000000101"
STAGING_HOST_UUID = "00000000-0000-4000-8000-000000000201"


def response(payload):
    return {"response": payload}


def subscription_url(username: str) -> str:
    return f"https://sub-staging.alanet.ru/sub/{username}"


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mock-remnawave", "time": datetime.now(UTC).isoformat()}


@app.get("/api/nodes")
async def list_nodes():
    return response(
        [
            {
                "name": "ALANET-STAGING-01",
                "uuid": STAGING_NODE_UUID,
                "address": "127.0.0.1",
                "countryCode": "ST",
                "isConnected": True,
                "version": "mock",
            }
        ]
    )


@app.get("/api/hosts")
async def list_hosts():
    return response(
        [
            {
                "remark": "Staging mock",
                "uuid": STAGING_HOST_UUID,
                "address": "remnawave-mock",
                "port": 8080,
                "nodes": [STAGING_NODE_UUID],
                "isDisabled": False,
            }
        ]
    )


@app.post("/api/users")
async def create_user(payload: dict):
    global next_user_id
    username = str(payload.get("username") or "").strip()
    if not username:
        raise HTTPException(status_code=422, detail="username is required")
    existing = users_by_username.get(username)
    if existing:
        return response({"user": existing})
    next_user_id += 1
    user = {
        "id": next_user_id,
        "uuid": str(uuid4()),
        "username": username,
        "status": payload.get("status", "ACTIVE"),
        "expireAt": payload.get("expireAt"),
        "trafficLimitBytes": payload.get("trafficLimitBytes"),
        "hwidDeviceLimit": payload.get("hwidDeviceLimit"),
        "activeInternalSquads": payload.get("activeInternalSquads", []),
        "subscriptionUrl": subscription_url(username),
    }
    users_by_username[username] = user
    users_by_id[next_user_id] = user
    return response({"user": user})


@app.get("/api/users/by-username/{username}")
async def get_user_by_username(username: str):
    user = users_by_username.get(username)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return response({"user": user})


@app.patch("/api/users")
async def update_user(payload: dict):
    user = None
    if payload.get("id") is not None:
        user = users_by_id.get(int(payload["id"]))
    if user is None and payload.get("uuid"):
        user = next((item for item in users_by_id.values() if item.get("uuid") == payload["uuid"]), None)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    for key, value in payload.items():
        if key not in {"id", "uuid"}:
            user[key] = value
    return response({"user": user})


@app.post("/api/users/{user_id}/actions/enable")
async def enable_user(user_id: int):
    return await update_user({"id": user_id, "status": "ACTIVE"})


@app.post("/api/users/{user_id}/actions/disable")
async def disable_user(user_id: int):
    return await update_user({"id": user_id, "status": "DISABLED"})


@app.post("/api/users/{user_id}/actions/revoke")
async def revoke_user(user_id: int):
    return await update_user({"id": user_id, "status": "DISABLED", "revoked": True})
