export interface User {
  pk: number;
  username: string;
  name: string;
  email: string;
  phone?: string;
  is_active: boolean;
  is_superuser: boolean;
  groups: string[];
  avatar?: string;
  last_login?: string;
  attributes?: Record<string, any>;
}

export interface BoundGroupRef {
  pk: string;
  name: string;
  is_granular_user: boolean;
  is_granular_admin: boolean;
  is_admin_group: boolean;
}

export interface Application {
  pk: string;
  name: string;
  slug: string;
  group?: string;
  meta_icon?: string;
  meta_description?: string;
  launch_url?: string;
  is_protected: boolean;
  bound_group_pk?: string;
  bound_group_name?: string;
  granular_user_group_pk?: string;
  granular_user_group_name?: string;
  granular_admin_group_pk?: string;
  granular_admin_group_name?: string;
  has_granular_user_group: boolean;
  has_granular_admin_group: boolean;
  all_bound_groups: BoundGroupRef[];
}

export interface ExpiringGrant {
  id?: number;
  user_pk: number;
  user_name: string;
  app_pk: string;
  app_name: string;
  group_pk: string;
  role: 'member' | 'admin';
  expires_at: string;
  created_at: string;
  is_revoked: boolean;
}

export interface AccessTemplate {
  id: number;
  name: string;
  description?: string;
  icon: string;
  assignments: Record<string, 'member' | 'admin'>;
  created_at: string;
}

export interface AccessMatrixData {
  users: User[];
  apps: Application[];
  permissions: Record<string, Record<string, boolean>>; // user_pk -> { app_pk -> bool }
  admin_permissions?: Record<string, Record<string, boolean>>; // user_pk -> { app_pk -> bool }
  inherited_access?: Record<string, Record<string, string[]>>; // user_pk -> { app_pk -> string[] }
  app_group_map: Record<string, string | null>;
  app_admin_group_map?: Record<string, string | null>;
  expiring_grants?: Record<string, Record<string, ExpiringGrant>>; // user_pk -> { app_pk -> ExpiringGrant }
}

export interface StagedChange {
  user_pk: number;
  userName: string;
  app_pk: string;
  appName: string;
  group_pk: string;
  grant: boolean;
  duration_hours?: number;
}

export interface TrackedInvite {
  id: number;
  invitation_pk: string;
  name: string;
  email?: string;
  phone?: string;
  whatsapp_sent?: boolean;
  expires_at?: string;
  single_use: boolean;
  assigned_groups: string[];
  assigned_apps: string[];
  invite_url: string;
  status: 'pending' | 'redeemed' | 'revoked' | 'expired';
  redeemed_by?: string;
  created_at: string;
}

export interface WhatsAppStatus {
  status: 'connected' | 'qr_ready' | 'connecting' | 'disconnected' | 'service_offline' | 'disabled';
  phone: string | null;
  qrCodeDataUrl: string | null;
  lastConnected: string | null;
  available: boolean;
}

export interface HealthStatus {
  status: string;
  authentik_connected: boolean;
  connection_error?: string | null;
  authentik_url: string;
  demo_mode: boolean;
  auth_method: 'none' | 'password' | 'forward_auth' | 'oidc';
  total_users: number;
  total_apps: number;
  unprotected_apps_count: number;
  active_invites_count: number;
}

export interface AuthStatus {
  authenticated: boolean;
  auth_method: string;
  user?: string;
  is_admin: boolean;
  demo_mode: boolean;
}

export interface AuditLog {
  id: number;
  timestamp: string;
  actor: string;
  action: string;
  target_type: string;
  target_name: string;
  target_id: string;
  details?: string;
  status: string;
}

export interface AppSettings {
  authentik_url: string;
  authentik_token_masked: string;
  authentik_token_configured: boolean;
  authentik_insecure_skip_verify: boolean;
  app_group_prefix: string;
  default_enrollment_flow: string;
  whatsapp_enabled: boolean;
  whatsapp_service_url: string;
  default_country_code: string;
  custom_invite_message?: string | null;
  notification_webhook_url?: string | null;
  ntfy_topic?: string | null;
  ntfy_server_url: string;
  admin_phone_numbers?: string | null;
  telegram_enabled: boolean;
  telegram_bot_token_masked?: string | null;
  telegram_bot_token_configured: boolean;
  telegram_admin_chat_ids?: string | null;
  default_lease_duration_hours: number;
  default_invite_expiry_days: number;
  // OIDC & Security Settings
  auth_method: 'none' | 'password' | 'forward_auth' | 'oidc';
  admin_password_configured: boolean;
  webhook_secret_configured?: boolean;
  webhook_secret_masked?: string | null;
  app_url?: string | null;
  oidc_client_id?: string | null;
  oidc_client_secret_masked?: string | null;
  oidc_client_secret_configured: boolean;
  oidc_issuer_url?: string | null;
  oidc_redirect_uri?: string | null;
  oidc_admin_group?: string | null;
  oidc_configured: boolean;
}

export interface UpdateSettingsPayload {
  authentik_url?: string;
  authentik_token?: string;
  authentik_insecure_skip_verify?: boolean;
  app_group_prefix?: string;
  default_enrollment_flow?: string;
  whatsapp_enabled?: boolean;
  whatsapp_service_url?: string;
  default_country_code?: string;
  custom_invite_message?: string | null;
  notification_webhook_url?: string | null;
  ntfy_topic?: string | null;
  ntfy_server_url?: string | null;
  admin_phone_numbers?: string | null;
  telegram_enabled?: boolean;
  telegram_bot_token?: string | null;
  telegram_admin_chat_ids?: string | null;
  default_lease_duration_hours?: number;
  default_invite_expiry_days?: number;
  // OIDC & Security Settings
  auth_method?: string;
  admin_password?: string;
  webhook_secret?: string;
  app_url?: string;
  oidc_client_id?: string;
  oidc_client_secret?: string;
  oidc_issuer_url?: string;
  oidc_redirect_uri?: string;
  oidc_admin_group?: string;
}

export interface AutoSetupOidcPayload {
  app_url?: string;
  app_name?: string;
  app_slug?: string;
  admin_group_name?: string;
  activate_immediately?: boolean;
}

export interface AutoSetupOidcResult {
  success: boolean;
  message: string;
  app_url: string;
  provider_pk?: any;
  provider_name: string;
  client_id: string;
  client_secret_masked: string;
  issuer_url: string;
  redirect_uri: string;
  application_pk?: string;
  application_slug: string;
  bound_group_name: string;
  bound_group_pk?: string;
  auth_method: string;
  steps_completed: string[];
}

export interface TestConnectionResult {
  success: boolean;
  version?: string | null;
  error?: string | null;
}

export interface TestTelegramResult {
  success: boolean;
  bot_username?: string | null;
  first_name?: string | null;
  error?: string | null;
}

export interface TestNotificationResult {
  success: boolean;
  results: Record<string, any>;
}

