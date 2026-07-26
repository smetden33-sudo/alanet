from datetime import datetime
from typing import Any
import httpx
from ..config import Settings


class RemnawaveError(RuntimeError):
    pass


class RemnawaveClient:
    """Adapter for Remnawave v3. Pin the Panel version in production and run contract tests on upgrades."""

    def __init__(self, settings: Settings):
        self.base_url = settings.remnawave_base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {settings.remnawave_token.get_secret_value()}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20, headers=self.headers) as client:
            response = await client.request(method, f"{self.base_url}{path}", **kwargs)
        if response.status_code >= 400:
            raise RemnawaveError(f"Remnawave {method} {path} failed: HTTP {response.status_code}")
        body = response.json()
        return body.get("response", body)

    async def create_user(self, *, username: str, expire_at: datetime, traffic_limit_bytes: int, device_limit: int, squad_id: str) -> dict[str, Any]:
        payload = {
            "username": username,
            "status": "ACTIVE",
            "expireAt": expire_at.isoformat(),
            "trafficLimitBytes": traffic_limit_bytes,
            "trafficLimitStrategy": "NO_RESET",
            "hwidDeviceLimit": device_limit,
            "activeInternalSquads": [squad_id],
        }
        return await self._request("POST", "/api/users", json=payload)

    async def get_user_by_username(self, username: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/users/by-username/{username}")

    async def list_nodes(self) -> list[dict[str, Any]]:
        response = await self._request("GET", "/api/nodes")
        return response if isinstance(response, list) else response.get("nodes", [])

    async def update_user(self, user_id: int, *, user_uuid: str | None = None, **changes: Any) -> dict[str, Any]:
        identifier = {"uuid": user_uuid} if user_uuid else {"id": user_id}
        return await self._request("PATCH", "/api/users", json={**identifier, **changes})

    async def extend_subscription(self, user_id: int, expire_at: datetime, *, user_uuid: str | None = None) -> dict[str, Any]:
        return await self.update_user(user_id, user_uuid=user_uuid, expireAt=expire_at.isoformat(), status="ACTIVE")

    async def enable_user(self, user_id: int) -> dict[str, Any]:
        return await self._request("POST", f"/api/users/{user_id}/actions/enable")

    async def disable_user(self, user_id: int) -> dict[str, Any]:
        return await self._request("POST", f"/api/users/{user_id}/actions/disable")

    async def revoke_subscription(self, user_id: int) -> dict[str, Any]:
        return await self._request("POST", f"/api/users/{user_id}/actions/revoke")

    def user_fields(self, payload: dict[str, Any]) -> tuple[int, str, str | None]:
        user = payload.get("user", payload)
        user_id = int(user["id"])
        subscription_url = user.get("subscriptionUrl") or user.get("subscriptionUrlPath")
        if not subscription_url:
            raise RemnawaveError("Remnawave response has no subscription URL")
        if subscription_url.startswith("/"):
            subscription_url = f"{self.base_url}{subscription_url}"
        return user_id, subscription_url, user.get("uuid")
