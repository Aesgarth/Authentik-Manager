from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

# --- User & Group Models ---

class UserSchema(BaseModel):
    pk: int
    username: str
    name: str = ""
    email: Optional[str] = ""
    is_active: bool = True
    is_superuser: bool = False
    groups: List[str] = [] # List of Group UUIDs
    avatar: Optional[str] = None
    last_login: Optional[str] = None

class GroupSchema(BaseModel):
    pk: str # UUID
    name: str
    is_superuser: bool = False
    users: List[int] = []

class BoundGroupRef(BaseModel):
    pk: str
    name: str
    is_granular_user: bool = False
    is_granular_admin: bool = False
    is_admin_group: bool = False

class ApplicationSchema(BaseModel):
    pk: str # UUID
    name: str
    slug: str
    group: Optional[str] = None # Category in Authentik UI
    meta_icon: Optional[str] = None
    meta_description: Optional[str] = None
    launch_url: Optional[str] = None
    is_protected: bool = False # Has at least 1 policy binding or bound group
    bound_group_pk: Optional[str] = None
    bound_group_name: Optional[str] = None

    # Granular RBAC Groups
    granular_user_group_pk: Optional[str] = None
    granular_user_group_name: Optional[str] = None
    granular_admin_group_pk: Optional[str] = None
    granular_admin_group_name: Optional[str] = None
    has_granular_user_group: bool = False
    has_granular_admin_group: bool = False
    all_bound_groups: List[BoundGroupRef] = []

# --- Expiring Access Grant Models ---

class ExpiringGrantSchema(BaseModel):
    id: Optional[int] = None
    user_pk: int
    user_name: str
    app_pk: str
    app_name: str
    group_pk: str
    role: str # 'member' | 'admin'
    expires_at: str # ISO 8601
    created_at: str
    is_revoked: bool = False

class CreateExpiringGrantRequest(BaseModel):
    user_pk: int
    user_name: str
    app_pk: str
    app_name: str
    group_pk: str
    role: str = "member"
    duration_hours: Optional[int] = None # e.g. 24, 72, 168 (7d), 720 (30d)
    expires_at: Optional[str] = None # Explicit ISO 8601 datetime

class RevokeExpiringGrantRequest(BaseModel):
    user_pk: int
    app_pk: str
    group_pk: str

# --- Access Templates / Personas Models ---

class AccessTemplateSchema(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    icon: str = "shield"
    assignments: Dict[str, str] # app_pk or slug -> 'member' | 'admin'
    created_at: str

class CreateAccessTemplateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = "shield"
    assignments: Dict[str, str]

class ApplyAccessTemplateRequest(BaseModel):
    template_id: int
    user_pk: int
    user_name: str
    duration_hours: Optional[int] = None # Optional lease in hours

# --- Access Matrix Models ---

class AccessMatrixResponse(BaseModel):
    users: List[UserSchema]
    apps: List[ApplicationSchema]
    # user_pk -> { app_pk: bool } (True if user has access either direct, admin, or inherited)
    permissions: Dict[str, Dict[str, bool]]
    # user_pk -> { app_pk: bool } (True if user is in granular admin group or is superuser)
    admin_permissions: Dict[str, Dict[str, bool]] = {}
    # user_pk -> { app_pk: list of inherited group names e.g. ["5AMT Home"] }
    inherited_access: Dict[str, Dict[str, List[str]]] = {}
    # Mapping app_pk -> bound user group_pk for fast lookups
    app_group_map: Dict[str, Optional[str]]
    # Mapping app_pk -> bound admin group_pk
    app_admin_group_map: Dict[str, Optional[str]] = {}
    # Active expiring grants: user_pk -> { app_pk: ExpiringGrantSchema }
    expiring_grants: Dict[str, Dict[str, ExpiringGrantSchema]] = {}

class TogglePermissionRequest(BaseModel):
    user_pk: int
    app_pk: str
    group_pk: str
    grant: bool
    duration_hours: Optional[int] = None

class BulkToggleRequest(BaseModel):
    changes: List[TogglePermissionRequest]

# --- Provisioning Models ---

class ProvisionAppGroupRequest(BaseModel):
    app_pk: str
    group_name: Optional[str] = None # Defaults to "App - {AppName}"
    create_user_group: bool = True
    create_admin_group: bool = True
    custom_user_group_name: Optional[str] = None
    custom_admin_group_name: Optional[str] = None

class ProvisionAllRequest(BaseModel):
    create_user_groups: bool = True
    create_admin_groups: bool = True
    include_already_secured: bool = True

class ProvisionAppGroupDetail(BaseModel):
    app_pk: str
    app_name: str
    user_group_pk: Optional[str] = None
    user_group_name: Optional[str] = None
    user_group_created: bool = False
    admin_group_pk: Optional[str] = None
    admin_group_name: Optional[str] = None
    admin_group_created: bool = False
    user_binding_created: bool = False
    admin_binding_created: bool = False

class ProvisionAllUnprotectedResponse(BaseModel):
    provisioned_count: int
    provisioned_apps: List[str]
    details: List[ProvisionAppGroupDetail] = []

# --- Invitation Models ---

class CreateInviteRequest(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    send_via_whatsapp: bool = False
    custom_message: Optional[str] = None
    expires_in_days: int = 7
    single_use: bool = True
    group_pks: List[str]
    app_names: List[str] = []

class TrackedInviteSchema(BaseModel):
    id: int
    invitation_pk: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp_sent: bool = False
    expires_at: Optional[str] = None
    single_use: bool = True
    assigned_groups: List[str]
    assigned_apps: List[str]
    invite_url: str
    status: str
    redeemed_by: Optional[str] = None
    created_at: str

# --- WhatsApp Models ---

class WhatsAppStatusResponse(BaseModel):
    status: str # 'connected', 'qr_ready', 'connecting', 'disconnected'
    phone: Optional[str] = None
    qrCodeDataUrl: Optional[str] = None
    lastConnected: Optional[str] = None
    available: bool = True

class WhatsAppSendRequest(BaseModel):
    recipient: str
    message: str

class WhatsAppSendResponse(BaseModel):
    success: bool
    messageId: Optional[str] = None
    error: Optional[str] = None

# --- Auth Models ---

class LoginRequest(BaseModel):
    password: str

class AuthStatus(BaseModel):
    authenticated: bool
    auth_method: str
    user: Optional[str] = None
    is_admin: bool = True
    demo_mode: bool = False

# --- Health & Stats Models ---

class HealthResponse(BaseModel):
    status: str
    authentik_connected: bool
    connection_error: Optional[str] = None
    authentik_url: str
    demo_mode: bool
    auth_method: str
    total_users: int
    total_apps: int
    unprotected_apps_count: int
    active_invites_count: int

# --- Settings & Admin Panel Models ---

class SettingsResponse(BaseModel):
    authentik_url: str
    authentik_token_masked: str
    authentik_token_configured: bool
    authentik_insecure_skip_verify: bool
    app_group_prefix: str
    default_enrollment_flow: str
    whatsapp_enabled: bool
    whatsapp_service_url: str
    default_country_code: str
    custom_invite_message: Optional[str] = None
    notification_webhook_url: Optional[str] = None
    default_lease_duration_hours: int = 72
    default_invite_expiry_days: int = 7

class UpdateSettingsRequest(BaseModel):
    authentik_url: Optional[str] = None
    authentik_token: Optional[str] = None
    authentik_insecure_skip_verify: Optional[bool] = None
    app_group_prefix: Optional[str] = None
    default_enrollment_flow: Optional[str] = None
    whatsapp_enabled: Optional[bool] = None
    whatsapp_service_url: Optional[str] = None
    default_country_code: Optional[str] = None
    custom_invite_message: Optional[str] = None
    notification_webhook_url: Optional[str] = None
    default_lease_duration_hours: Optional[int] = None
    default_invite_expiry_days: Optional[int] = None

class TestConnectionRequest(BaseModel):
    url: Optional[str] = None
    token: Optional[str] = None
    insecure_skip_verify: Optional[bool] = None

class TestConnectionResponse(BaseModel):
    success: bool
    version: Optional[str] = None
    error: Optional[str] = None
