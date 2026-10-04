import uuid
import re
import secrets
import logging
import httpx
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from app.config import settings

logger = logging.getLogger("authentik_manager.authentik_client")

class AuthentikClient:
    def __init__(self):
        self.mock_applications = []
        self.mock_groups = []
        self.mock_users = []
        self.mock_policy_bindings = []
        self.mock_invites = []
        self.mock_oauth2_providers = []
        self.mock_flows = []
        self.mock_scope_mappings = []
        self.mock_expression_policies = []
        self.mock_events = []
        if settings.DEMO_MODE:
            self._init_mock_store()

    @property
    def base_url(self) -> str:
        return settings.AUTHENTIK_URL.rstrip("/")

    @property
    def token(self) -> str:
        return settings.AUTHENTIK_TOKEN

    @property
    def verify_ssl(self) -> bool:
        return not settings.AUTHENTIK_INSECURE_SKIP_VERIFY

    @property
    def demo_mode(self) -> bool:
        return settings.DEMO_MODE

    @demo_mode.setter
    def demo_mode(self, val: bool):
        settings.DEMO_MODE = val

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        if not self.demo_mode:
            if not self.token or self.token == "your_authentik_api_bearer_token_here":
                raise ValueError(
                    "AUTHENTIK_TOKEN is not set in .env. Please generate an API token in Authentik and set AUTHENTIK_TOKEN in .env."
                )

        url = f"{self.base_url}{endpoint}"
        logger.debug(f"Authentik API Request: {method} {url}")
        try:
            async with httpx.AsyncClient(verify=self.verify_ssl, timeout=15.0) as client:
                response = await client.request(
                    method, url, headers=self._get_headers(), **kwargs
                )
                logger.debug(f"Authentik API Response: {method} {url} -> Status {response.status_code}")
                response.raise_for_status()
                if response.status_code == 204:
                    return None
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Authentik API HTTP error ({e.response.status_code}) on {method} {url}: {e.response.text[:500]}")
            if e.response.status_code in (401, 403):
                raise RuntimeError(
                    f"Authentik API token rejected (HTTP {e.response.status_code}). Verify your token in .env and ensure the service account has admin permissions."
                )
            raise RuntimeError(f"Authentik API error ({e.response.status_code}): {e.response.text[:200]}")
        except httpx.ConnectError as e:
            logger.error(f"Authentik API ConnectError on {method} {url}: {e}")
            raise RuntimeError(
                f"Failed to connect to Authentik at '{self.base_url}'. Check your AUTHENTIK_URL in .env and verify the host is reachable."
            )
        except Exception as e:
            logger.error(f"Authentik API unexpected error on {method} {url}: {e}", exc_info=True)
            raise

    async def _get_all_paginated(self, endpoint: str, params: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Handles Authentik pagination to retrieve all items."""
        all_results = []
        current_endpoint = endpoint
        current_params = params or {"page_size": 100}

        while current_endpoint:
            data = await self._request("GET", current_endpoint, params=current_params)
            if isinstance(data, dict) and "results" in data:
                all_results.extend(data["results"])
                # Next page URL
                next_url = data.get("next")
                if next_url:
                    # Strip base_url if present
                    if next_url.startswith(self.base_url):
                        current_endpoint = next_url[len(self.base_url):]
                    else:
                        current_endpoint = next_url
                    current_params = None  # query params are already in next URL
                else:
                    break
            elif isinstance(data, list):
                all_results.extend(data)
                break
            else:
                break

        return all_results

    # ==================== Real API Methods ====================

    async def test_connection(self) -> tuple[bool, Optional[str]]:
        if self.demo_mode:
            return True, None
        if not self.token or self.token == "your_authentik_api_bearer_token_here":
            return False, "AUTHENTIK_TOKEN is missing or using placeholder in .env"

        try:
            res = await self._request("GET", "/api/v3/core/users/me/")
            if isinstance(res, dict) and ("user" in res or "username" in res or "pk" in res):
                return True, None
            return False, "Unexpected response from Authentik"
        except Exception as e:
            return False, str(e)

    async def get_applications(self) -> List[Dict[str, Any]]:
        if self.demo_mode:
            return self.mock_applications
        return await self._get_all_paginated("/api/v3/core/applications/")

    async def get_groups(self) -> List[Dict[str, Any]]:
        if self.demo_mode:
            return self.mock_groups
        return await self._get_all_paginated("/api/v3/core/groups/")

    async def get_users(self) -> List[Dict[str, Any]]:
        if self.demo_mode:
            return self.mock_users
        return await self._get_all_paginated("/api/v3/core/users/")

    async def get_policy_bindings(self, target_pk: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.demo_mode:
            if target_pk:
                return [b for b in self.mock_policy_bindings if b.get("target") == target_pk]
            return self.mock_policy_bindings
        params = {"page_size": 200}
        if target_pk:
            params["target"] = target_pk
        return await self._get_all_paginated("/api/v3/policies/bindings/", params=params)

    async def create_group(self, name: str, attributes: Optional[Dict] = None) -> Dict[str, Any]:
        if self.demo_mode:
            new_group = {
                "pk": str(uuid.uuid4()),
                "name": name,
                "is_superuser": False,
                "users": [1], # admin is automatically in the group
                "attributes": attributes or {},
            }
            self.mock_groups.append(new_group)
            return new_group

        payload = {
            "name": name,
            "is_superuser": False,
            "attributes": attributes or {},
        }
        return await self._request("POST", "/api/v3/core/groups/", json=payload)

    async def create_policy_binding(
        self,
        target_pk: str,
        group_pk: str,
        order: int = 0,
        negate: bool = False,
    ) -> Dict[str, Any]:
        if self.demo_mode:
            new_binding = {
                "pk": str(uuid.uuid4()),
                "target": target_pk,
                "group": group_pk,
                "order": order,
                "negate": negate,
                "enabled": True,
            }
            self.mock_policy_bindings.append(new_binding)
            return new_binding

        payload = {
            "target": target_pk,
            "group": group_pk,
            "order": order,
            "negate": negate,
            "enabled": True,
            "failure_result": False,
        }
        return await self._request("POST", "/api/v3/policies/bindings/", json=payload)

    async def set_app_policy_engine_mode(self, slug_or_pk: str, mode: str = "any") -> bool:
        """Sets the application's policy engine mode to 'any' (OR logic) or 'all' (AND logic)."""
        if self.demo_mode:
            return True
        try:
            await self._request("PATCH", f"/api/v3/core/applications/{slug_or_pk}/", json={"policy_engine_mode": mode})
            return True
        except Exception:
            return False

    async def add_user_to_group(self, group_pk: str, user_pk: int) -> bool:
        if self.demo_mode:
            for g in self.mock_groups:
                if g["pk"] == group_pk and user_pk not in g["users"]:
                    g["users"].append(user_pk)
            for u in self.mock_users:
                if u["pk"] == user_pk and group_pk not in u.get("groups", []):
                    u.setdefault("groups", []).append(group_pk)
            return True

        endpoint = f"/api/v3/core/groups/{group_pk}/add_user/"
        await self._request("POST", endpoint, json={"pk": user_pk})
        return True

    async def remove_user_from_group(self, group_pk: str, user_pk: int) -> bool:
        if self.demo_mode:
            for g in self.mock_groups:
                if g["pk"] == group_pk and user_pk in g["users"]:
                    g["users"].remove(user_pk)
            for u in self.mock_users:
                if u["pk"] == user_pk and group_pk in u.get("groups", []):
                    u["groups"].remove(group_pk)
            return True

        endpoint = f"/api/v3/core/groups/{group_pk}/remove_user/"
        await self._request("POST", endpoint, json={"pk": user_pk})
        return True

    async def create_invitation(
        self,
        name: str,
        expires: Optional[str],
        fixed_data: Dict[str, Any],
        single_use: bool = True
    ) -> Dict[str, Any]:
        # Defensively ensure name is a valid slug for Authentik (letters, numbers, underscores, hyphens; max 50)
        clean_name = re.sub(r'[^a-zA-Z0-9_-]+', '-', name.strip().lower()).strip('-')
        if not clean_name:
            clean_name = "invite"

        if re.match(r'^[a-zA-Z0-9_-]+$', name) and len(name) <= 50:
            slug = name
        else:
            slug = f"{clean_name[:38].strip('-')}-{secrets.token_hex(4)}"

        if self.demo_mode:
            new_invite = {
                "pk": str(uuid.uuid4()),
                "name": slug,
                "expires": expires,
                "fixed_data": fixed_data,
                "single_use": single_use,
            }
            self.mock_invites.append(new_invite)
            return new_invite

        payload = {
            "name": slug,
            "expires": expires,
            "fixed_data": fixed_data,
            "single_use": single_use,
        }
        return await self._request("POST", "/api/v3/stages/invitation/invitations/", json=payload)

    async def get_invitations(self) -> List[Dict[str, Any]]:
        if self.demo_mode:
            return self.mock_invites
        return await self._get_all_paginated("/api/v3/stages/invitation/invitations/")

    async def delete_invitation(self, invite_pk: str) -> bool:
        if self.demo_mode:
            self.mock_invites = [i for i in self.mock_invites if i["pk"] != invite_pk]
            return True
        await self._request("DELETE", f"/api/v3/stages/invitation/invitations/{invite_pk}/")
        return True

    async def get_events(self, action: Optional[str] = None, page_size: int = 50) -> List[Dict[str, Any]]:
        if self.demo_mode:
            if action:
                return [e for e in self.mock_events if e.get("action") == action]
            return self.mock_events
        params: Dict[str, Any] = {"page_size": page_size}
        if action:
            params["action"] = action
        try:
            res = await self._request("GET", "/api/v3/events/events/", params=params)
            if isinstance(res, dict) and "results" in res:
                return res["results"]
            elif isinstance(res, list):
                return res
            return []
        except Exception:
            return []

    async def get_expression_policies(self) -> List[Dict[str, Any]]:
        if self.demo_mode:
            return self.mock_expression_policies
        return await self._get_all_paginated("/api/v3/policies/expression/")

    async def create_expression_policy(self, name: str, expression: str) -> Dict[str, Any]:
        if self.demo_mode:
            new_pol = {"pk": str(uuid.uuid4()), "name": name, "expression": expression}
            self.mock_expression_policies.append(new_pol)
            return new_pol
        payload = {
            "name": name,
            "expression": expression,
            "execution_logging": True,
        }
        return await self._request("POST", "/api/v3/policies/expression/", json=payload)

    async def update_expression_policy(self, policy_pk: str, name: str, expression: str) -> Dict[str, Any]:
        if self.demo_mode:
            for p in self.mock_expression_policies:
                if p["pk"] == policy_pk:
                    p["name"] = name
                    p["expression"] = expression
                    return p
            return {"pk": policy_pk, "name": name, "expression": expression}
        payload = {
            "name": name,
            "expression": expression,
        }
        return await self._request("PATCH", f"/api/v3/policies/expression/{policy_pk}/", json=payload)

    async def bind_policy_to_flow(self, flow_pk: str, policy_pk: str, order: int = 0) -> Dict[str, Any]:
        if self.demo_mode:
            binding = {
                "pk": str(uuid.uuid4()),
                "target": flow_pk,
                "policy": policy_pk,
                "order": order,
                "enabled": True
            }
            self.mock_policy_bindings.append(binding)
            return binding
        payload = {
            "target": flow_pk,
            "policy": policy_pk,
            "order": order,
            "enabled": True,
            "failure_result": False,
        }
        return await self._request("POST", "/api/v3/policies/bindings/", json=payload)

    # ==================== Notification Transports & Rules ====================

    async def get_notification_transports(self) -> List[Dict[str, Any]]:
        if self.demo_mode:
            return getattr(self, "mock_transports", [])
        return await self._get_all_paginated("/api/v3/events/transports/")

    async def create_webhook_transport(self, name: str, webhook_url: str) -> Dict[str, Any]:
        if self.demo_mode:
            new_tr = {"pk": str(uuid.uuid4()), "name": name, "mode": "webhook", "webhook_url": webhook_url}
            if not hasattr(self, "mock_transports"):
                self.mock_transports = []
            self.mock_transports.append(new_tr)
            return new_tr
        payload = {
            "name": name,
            "mode": "webhook",
            "webhook_url": webhook_url,
            "send_once": False,
        }
        return await self._request("POST", "/api/v3/events/transports/", json=payload)

    async def get_notification_rules(self) -> List[Dict[str, Any]]:
        if self.demo_mode:
            return getattr(self, "mock_notification_rules", [])
        return await self._get_all_paginated("/api/v3/events/rules/")

    async def create_notification_rule(self, name: str, transports: List[str], severity: str = "notice") -> Dict[str, Any]:
        if self.demo_mode:
            new_r = {"pk": str(uuid.uuid4()), "name": name, "transports": transports, "severity": severity}
            if not hasattr(self, "mock_notification_rules"):
                self.mock_notification_rules = []
            self.mock_notification_rules.append(new_r)
            return new_r
        payload = {
            "name": name,
            "transports": transports,
            "severity": severity,
        }
        return await self._request("POST", "/api/v3/events/rules/", json=payload)

    # ==================== OIDC & Application Provisioning ====================

    async def get_flows(self, designation: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.demo_mode:
            if designation:
                return [f for f in self.mock_flows if f.get("designation") == designation]
            return self.mock_flows
        params = {"designation": designation} if designation else None
        return await self._get_all_paginated("/api/v3/flows/instances/", params=params)

    async def get_scope_mappings(self) -> List[Dict[str, Any]]:
        if self.demo_mode:
            return self.mock_scope_mappings
        return await self._get_all_paginated("/api/v3/propertymappings/provider/scope/")

    async def get_oauth2_providers(self, search: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.demo_mode:
            if search:
                return [p for p in self.mock_oauth2_providers if search.lower() in p.get("name", "").lower()]
            return self.mock_oauth2_providers
        params = {"search": search} if search else None
        return await self._get_all_paginated("/api/v3/providers/oauth2/", params=params)

    async def create_oauth2_provider(
        self,
        name: str,
        authorization_flow: str,
        client_id: str,
        client_secret: str,
        redirect_uris: Any,
        property_mappings: Optional[List[str]] = None,
        invalidation_flow: Optional[str] = None,
        client_type: str = "confidential",
        sub_mode: str = "hashed_user_id",
        include_claims_in_id_token: bool = True,
        issuer_mode: str = "per_provider"
    ) -> Dict[str, Any]:
        if self.demo_mode:
            new_provider = {
                "pk": len(self.mock_oauth2_providers) + 1,
                "name": name,
                "authorization_flow": authorization_flow,
                "invalidation_flow": invalidation_flow,
                "client_type": client_type,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": redirect_uris,
                "property_mappings": property_mappings or [],
                "sub_mode": sub_mode,
                "include_claims_in_id_token": include_claims_in_id_token,
                "issuer_mode": issuer_mode
            }
            self.mock_oauth2_providers.append(new_provider)
            return new_provider

        # Normalize redirect_uris for Authentik API
        # Modern Authentik (2024+) expects: [{"matching_mode": "strict", "url": "..."}]
        raw_uris = redirect_uris if isinstance(redirect_uris, list) else [redirect_uris]
        formatted_objects = []
        formatted_strings = []
        for u in raw_uris:
            if isinstance(u, dict):
                formatted_objects.append(u)
                formatted_strings.append(u.get("url", ""))
            else:
                formatted_objects.append({"matching_mode": "strict", "url": str(u)})
                formatted_strings.append(str(u))

        payload: Dict[str, Any] = {
            "name": name,
            "authorization_flow": authorization_flow,
            "client_type": client_type,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": formatted_objects,
            "sub_mode": sub_mode,
            "include_claims_in_id_token": include_claims_in_id_token,
            "issuer_mode": issuer_mode
        }
        if property_mappings:
            payload["property_mappings"] = property_mappings
        if invalidation_flow:
            payload["invalidation_flow"] = invalidation_flow

        try:
            return await self._request("POST", "/api/v3/providers/oauth2/", json=payload)
        except RuntimeError as e:
            # Fallback to string array if Authentik instance expects list of strings
            if "redirect_uris" in str(e).lower() and ("dictionary" in str(e).lower() or "string" in str(e).lower()):
                payload["redirect_uris"] = formatted_strings
                return await self._request("POST", "/api/v3/providers/oauth2/", json=payload)
            raise

    async def update_oauth2_provider(self, pk: Any, data: Dict[str, Any]) -> Dict[str, Any]:
        if self.demo_mode:
            for p in self.mock_oauth2_providers:
                if str(p.get("pk")) == str(pk):
                    p.update(data)
                    return p
            return {"pk": pk, **data}

        # Normalize redirect_uris if updated
        if "redirect_uris" in data:
            raw_uris = data["redirect_uris"] if isinstance(data["redirect_uris"], list) else [data["redirect_uris"]]
            formatted_objects = []
            formatted_strings = []
            for u in raw_uris:
                if isinstance(u, dict):
                    formatted_objects.append(u)
                    formatted_strings.append(u.get("url", ""))
                else:
                    formatted_objects.append({"matching_mode": "strict", "url": str(u)})
                    formatted_strings.append(str(u))

            data["redirect_uris"] = formatted_objects
            try:
                return await self._request("PATCH", f"/api/v3/providers/oauth2/{pk}/", json=data)
            except RuntimeError as e:
                if "redirect_uris" in str(e).lower():
                    data["redirect_uris"] = formatted_strings
                    return await self._request("PATCH", f"/api/v3/providers/oauth2/{pk}/", json=data)
                raise

        return await self._request("PATCH", f"/api/v3/providers/oauth2/{pk}/", json=data)

    async def get_application_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        if self.demo_mode:
            return next((a for a in self.mock_applications if a.get("slug") == slug), None)
        try:
            return await self._request("GET", f"/api/v3/core/applications/{slug}/")
        except Exception:
            return None

    async def create_application(
        self,
        name: str,
        slug: str,
        provider_pk: Optional[Any] = None,
        meta_launch_url: Optional[str] = None,
        meta_description: Optional[str] = None,
        meta_icon: Optional[str] = None,
        open_in_new_tab: bool = True
    ) -> Dict[str, Any]:
        if self.demo_mode:
            new_app = {
                "pk": str(uuid.uuid4()),
                "name": name,
                "slug": slug,
                "provider": provider_pk,
                "meta_launch_url": meta_launch_url,
                "meta_description": meta_description,
                "meta_icon": meta_icon,
                "open_in_new_tab": open_in_new_tab
            }
            self.mock_applications.append(new_app)
            return new_app

        payload: Dict[str, Any] = {
            "name": name,
            "slug": slug,
            "open_in_new_tab": open_in_new_tab
        }
        if provider_pk is not None:
            try:
                payload["provider"] = int(provider_pk)
            except (ValueError, TypeError):
                payload["provider"] = provider_pk
        if meta_launch_url:
            payload["meta_launch_url"] = meta_launch_url
        if meta_description:
            payload["meta_description"] = meta_description
        if meta_icon:
            payload["meta_icon"] = meta_icon

        return await self._request("POST", "/api/v3/core/applications/", json=payload)

    async def update_application(self, slug_or_pk: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if self.demo_mode:
            for a in self.mock_applications:
                if a.get("slug") == slug_or_pk or str(a.get("pk")) == str(slug_or_pk):
                    a.update(data)
                    return a
            return {"pk": slug_or_pk, **data}
        if "provider" in data and data["provider"] is not None:
            try:
                data["provider"] = int(data["provider"])
            except (ValueError, TypeError):
                pass
        return await self._request("PATCH", f"/api/v3/core/applications/{slug_or_pk}/", json=data)

    # ==================== Mock Store Initialization ====================

    def _init_mock_store(self):
        # Sample apps
        jellyfin_pk = "a1111111-1111-1111-1111-111111111111"
        nextcloud_pk = "a2222222-2222-2222-2222-222222222222"
        hass_pk = "a3333333-3333-3333-3333-333333333333"
        paperless_pk = "a4444444-4444-4444-4444-444444444444"
        unprotected_pk = "a5555555-5555-5555-5555-555555555555"

        # Sample groups
        g_admin_pk = "g0000000-0000-0000-0000-000000000000"
        g_jellyfin_pk = "g1111111-1111-1111-1111-111111111111"
        g_nextcloud_pk = "g2222222-2222-2222-2222-222222222222"
        g_hass_pk = "g3333333-3333-3333-3333-333333333333"

        self.mock_applications = [
            {
                "pk": jellyfin_pk,
                "name": "Jellyfin Media",
                "slug": "jellyfin",
                "group": "Media",
                "meta_icon": "https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/jellyfin.svg",
                "meta_description": "Home movie and TV show streaming",
                "launch_url": "https://jellyfin.lan",
            },
            {
                "pk": nextcloud_pk,
                "name": "Nextcloud",
                "slug": "nextcloud",
                "group": "Cloud",
                "meta_icon": "https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/nextcloud.svg",
                "meta_description": "Cloud file storage and photo backup",
                "launch_url": "https://nextcloud.lan",
            },
            {
                "pk": hass_pk,
                "name": "Home Assistant",
                "slug": "home-assistant",
                "group": "Smart Home",
                "meta_icon": "https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/home-assistant.svg",
                "meta_description": "Smart home automation controller",
                "launch_url": "https://hass.lan",
            },
            {
                "pk": paperless_pk,
                "name": "Paperless-ngx",
                "slug": "paperless",
                "group": "Productivity",
                "meta_icon": "https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/paperless-ngx.svg",
                "meta_description": "Document indexing and archiving",
                "launch_url": "https://paperless.lan",
            },
            {
                "pk": unprotected_pk,
                "name": "Proxmox Backup Server",
                "slug": "pbs",
                "group": "Infrastructure",
                "meta_icon": "https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/proxmox.svg",
                "meta_description": "Hypervisor backup target (UNPROTECTED: Open to all!)",
                "launch_url": "https://pbs.lan",
            },
        ]

        self.mock_groups = [
            {
                "pk": g_admin_pk,
                "name": "authentik Admins",
                "is_superuser": True,
                "users": [1],
                "attributes": {},
            },
            {
                "pk": g_jellyfin_pk,
                "name": f"{settings.APP_GROUP_PREFIX}Jellyfin Media",
                "is_superuser": False,
                "users": [1, 2, 3],
                "attributes": {},
            },
            {
                "pk": g_nextcloud_pk,
                "name": f"{settings.APP_GROUP_PREFIX}Nextcloud",
                "is_superuser": False,
                "users": [1, 2],
                "attributes": {},
            },
            {
                "pk": g_hass_pk,
                "name": f"{settings.APP_GROUP_PREFIX}Home Assistant",
                "is_superuser": False,
                "users": [1],
                "attributes": {},
            },
        ]

        self.mock_users = [
            {
                "pk": 1,
                "username": "alex",
                "name": "Alex W (Admin)",
                "email": "alex@home.lan",
                "is_active": True,
                "is_superuser": True,
                "groups": [g_admin_pk, g_jellyfin_pk, g_nextcloud_pk, g_hass_pk],
                "last_login": datetime.now(timezone.utc).isoformat(),
                "avatar": "https://api.dicebear.com/7.x/bottts/svg?seed=alex",
            },
            {
                "pk": 2,
                "username": "sarah",
                "name": "Sarah W",
                "email": "sarah@home.lan",
                "is_active": True,
                "is_superuser": False,
                "groups": [g_jellyfin_pk, g_nextcloud_pk],
                "last_login": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(),
                "avatar": "https://api.dicebear.com/7.x/bottts/svg?seed=sarah",
            },
            {
                "pk": 3,
                "username": "grandpa",
                "name": "Grandpa Joe",
                "email": "joe@family.net",
                "is_active": True,
                "is_superuser": False,
                "groups": [g_jellyfin_pk],
                "last_login": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
                "avatar": "https://api.dicebear.com/7.x/bottts/svg?seed=grandpa",
            },
            {
                "pk": 4,
                "username": "guest_charlie",
                "name": "Charlie Guest",
                "email": "charlie@external.com",
                "is_active": False,
                "is_superuser": False,
                "groups": [],
                "last_login": None,
                "avatar": "https://api.dicebear.com/7.x/bottts/svg?seed=charlie",
            },
        ]

        self.mock_policy_bindings = [
            {
                "pk": "b1111111-1111-1111-1111-111111111111",
                "target": jellyfin_pk,
                "group": g_jellyfin_pk,
                "order": 0,
                "negate": False,
                "enabled": True,
            },
            {
                "pk": "b2222222-2222-2222-2222-222222222222",
                "target": nextcloud_pk,
                "group": g_nextcloud_pk,
                "order": 0,
                "negate": False,
                "enabled": True,
            },
            {
                "pk": "b3333333-3333-3333-3333-333333333333",
                "target": hass_pk,
                "group": g_hass_pk,
                "order": 0,
                "negate": False,
                "enabled": True,
            },
            # Notice: paperless and unprotected_pk have NO bindings!
        ]

        self.mock_invites = []
        self.mock_oauth2_providers = []
        self.mock_flows = [
            {
                "pk": "flow-auth-implicit-pk",
                "name": "default-provider-authorization-implicit-consent",
                "slug": "default-provider-authorization-implicit-consent",
                "designation": "authorization",
            },
            {
                "pk": "flow-invalidation-pk",
                "name": "default-invalidation-flow",
                "slug": "default-invalidation-flow",
                "designation": "invalidation",
            },
        ]
        self.mock_scope_mappings = [
            {
                "pk": "scope-openid-pk",
                "name": "authentik default OAuth Mapping: OpenID 'openid'",
                "scope_name": "openid",
                "managed": "goauthentik.io/providers/oauth2/scope-openid",
            },
            {
                "pk": "scope-email-pk",
                "name": "authentik default OAuth Mapping: OpenID 'email'",
                "scope_name": "email",
                "managed": "goauthentik.io/providers/oauth2/scope-email",
            },
            {
                "pk": "scope-profile-pk",
                "name": "authentik default OAuth Mapping: OpenID 'profile'",
                "scope_name": "profile",
                "managed": "goauthentik.io/providers/oauth2/scope-profile",
            },
        ]

authentik_client = AuthentikClient()
