export interface User {
  pk: number;
  username: string;
  name: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  groups: string[];
  avatar?: string;
  last_login?: string;
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
}

export interface AccessMatrixData {
  users: User[];
  apps: Application[];
  permissions: Record<string, Record<string, boolean>>; // user_pk -> { app_pk -> bool }
  app_group_map: Record<string, string | null>;
}

export interface StagedChange {
  user_pk: number;
  userName: string;
  app_pk: string;
  appName: string;
  group_pk: string;
  grant: boolean;
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
