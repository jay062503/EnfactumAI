"""Identity resolution.

The assistant never owns user identity or permissions. It resolves them from Enfactum OS on every request
(cached briefly) and forwards the user's own credentials to OS tool calls, so the OS keeps enforcing its
existing middleware, policies and row-level rules.
"""
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt
import yaml
from fastapi import HTTPException, Request

from .config import Settings, csv_list, get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class UserContext:
    id: str
    name: str
    email: str = ""
    roles: frozenset[str] = field(default_factory=frozenset)
    permissions: frozenset[str] = field(default_factory=frozenset)
    user_type: str = "employee"
    # Credentials forwarded to Enfactum OS. Never serialised, logged or shown to the LLM.
    os_token: str | None = field(default=None, repr=False)
    os_cookies: str | None = field(default=None, repr=False)

    @property
    def is_admin(self) -> bool:
        return bool(self.roles & get_settings().admin_role_set)

    def can(self, permission: str | None) -> bool:
        if not permission:
            return True
        return self.is_admin or permission in self.permissions

    @property
    def allowed_in_app(self) -> bool:
        return self.user_type in set(csv_list(get_settings().allowed_user_types))

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "email": self.email, "user_type": self.user_type,
                "roles": sorted(self.roles), "is_admin": self.is_admin}


def resolve_user_type(explicit: Any, roles: frozenset[str]) -> str:
    """Enfactum OS has two kinds of accounts: employees and clients. Prefer an explicit OS field; otherwise a
    user holding only client roles is a client."""
    if explicit:
        value = str(explicit).strip().lower()
        return "client" if value in ("client", "customer", "external") else value
    client_roles = set(csv_list(get_settings().client_roles))
    if roles and roles <= client_roles:
        return "client"
    return "employee"


def _dig(data: Any, path: str) -> Any:
    for part in path.split(".") if path else []:
        if isinstance(data, dict):
            data = data.get(part)
        else:
            return None
    return data


def _names(value: Any) -> frozenset[str]:
    if not value:
        return frozenset()
    if isinstance(value, str):
        return frozenset(csv_list(value))
    if isinstance(value, dict):
        value = list(value.values())
    out = set()
    for item in value:
        if isinstance(item, dict):
            item = item.get("name") or item.get("slug")
        if item:
            out.add(str(item))
    return frozenset(out)


class AuthService:
    def __init__(self, settings: Settings, http: httpx.AsyncClient):
        self.s = settings
        self.http = http
        self._cache: dict[str, tuple[float, UserContext]] = {}
        self.demo_users: dict[str, dict] = {}
        if settings.auth_mode == "demo":
            if settings.is_production:
                raise RuntimeError("AUTH_MODE=demo is not allowed when ENVIRONMENT=production")
            self.demo_users = load_demo_users(settings)
            log.warning("AUTH_MODE=demo: identities are NOT verified. Use only for local evaluation.")
        self._jwt_key = None
        if settings.auth_mode == "jwt":
            self._jwt_key = (open(settings.jwt_public_key_file).read()
                             if settings.jwt_public_key_file else settings.jwt_secret)
            if not self._jwt_key:
                raise RuntimeError("AUTH_MODE=jwt requires JWT_SECRET or JWT_PUBLIC_KEY_FILE")

    async def authenticate(self, request: Request) -> UserContext:
        mode = self.s.auth_mode
        if mode == "demo":
            return self._demo(request)
        token = _bearer(request)
        cookies = request.headers.get("cookie") if self.s.os_forward_cookies else None
        if not token and not cookies:
            raise HTTPException(401, "Authentication required")
        cache_key = hashlib.sha256(f"{token}|{cookies}".encode()).hexdigest()
        hit = self._cache.get(cache_key)
        if hit and hit[0] > time.time():
            return hit[1]
        user = await self._laravel(token, cookies) if mode == "laravel" else self._jwt(token)
        self._cache[cache_key] = (time.time() + self.s.auth_cache_seconds, user)
        if len(self._cache) > 5000:
            now = time.time()
            self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
        return user

    def _demo(self, request: Request) -> UserContext:
        uid = request.headers.get("x-demo-user") or next(iter(self.demo_users), None)
        u = self.demo_users.get(uid or "")
        if not u:
            raise HTTPException(401, "Unknown demo user")
        roles = _names(u.get("roles"))
        return UserContext(id=str(u["id"]), name=u["name"], email=u.get("email", ""),
                           roles=roles, permissions=_names(u.get("permissions")),
                           user_type=resolve_user_type(u.get("user_type"), roles), os_token=u.get("os_token"))

    async def _laravel(self, token: str | None, cookies: str | None) -> UserContext:
        headers = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if cookies:
            headers["Cookie"] = cookies
        try:
            r = await self.http.get(self.s.os_base_url.rstrip("/") + self.s.os_user_endpoint, headers=headers,
                                    timeout=10)
        except httpx.HTTPError as exc:
            log.error("Enfactum OS identity endpoint unreachable: %s", exc)
            raise HTTPException(503, "Enfactum OS is unreachable") from exc
        if r.status_code in (401, 403, 419):
            raise HTTPException(401, "Enfactum OS rejected the credentials")
        if r.status_code >= 400:
            raise HTTPException(502, "Enfactum OS identity lookup failed")
        return self._map_claims(r.json(), token, cookies)

    def _jwt(self, token: str | None) -> UserContext:
        if not token:
            raise HTTPException(401, "Bearer token required")
        try:
            claims = jwt.decode(token, self._jwt_key, algorithms=csv_list(self.s.jwt_algorithms),
                                audience=self.s.jwt_audience or None, issuer=self.s.jwt_issuer or None,
                                options={"verify_aud": bool(self.s.jwt_audience)})
        except jwt.PyJWTError as exc:
            raise HTTPException(401, "Invalid token") from exc
        if self.s.os_user_id_field not in claims and "sub" in claims:
            claims[self.s.os_user_id_field] = claims["sub"]
        return self._map_claims(claims, token, None)

    def _map_claims(self, data: dict, token: str | None, cookies: str | None) -> UserContext:
        uid = _dig(data, self.s.os_user_id_field)
        if uid is None:
            raise HTTPException(502, "Identity payload has no user id")
        roles = _names(_dig(data, self.s.os_user_roles_field))
        return UserContext(
            id=str(uid),
            name=str(_dig(data, self.s.os_user_name_field) or f"User {uid}"),
            email=str(_dig(data, self.s.os_user_email_field) or ""),
            roles=roles,
            permissions=_names(_dig(data, self.s.os_user_permissions_field)),
            user_type=resolve_user_type(_dig(data, self.s.os_user_type_field), roles),
            os_token=token, os_cookies=cookies,
        )


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


def load_demo_users(settings: Settings) -> dict[str, dict]:
    with open(settings.demo_users_file) as fh:
        data = yaml.safe_load(fh) or {}
    return {str(u["id"]): u for u in data.get("users", [])}
