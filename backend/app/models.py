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

# --- Access Matrix Models ---

class AccessMatrixResponse(BaseModel):
    users: List[UserSchema]
    apps: List[ApplicationSchema]
    # user_pk -> { app_pk: bool }
    permissions: Dict[str, Dict[str, bool]]
    # Mapping app_pk -> bound group_pk for fast lookups
    app_group_map: Dict[str, Optional[str]]

class TogglePermissionRequest(BaseModel):
    user_pk: int
    app_pk: str
    group_pk: str
    grant: bool

class BulkToggleRequest(BaseModel):
    changes: List[TogglePermissionRequest]

# --- Provisioning Models ---

class ProvisionAppGroupRequest(BaseModel):
    app_pk: str
    group_name: Optional[str] = None # Defaults to "App - {AppName}"

class ProvisionAllUnprotectedResponse(BaseModel):
    provisioned_count: int
    provisioned_apps: List[str]

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
