import { 
  AccessMatrixData, 
  HealthStatus, 
  AuthStatus, 
  TrackedInvite, 
  AuditLog, 
  StagedChange, 
  ExpiringGrant, 
  AccessTemplate,
  AppSettings,
  UpdateSettingsPayload,
  TestConnectionResult,
  TestNotificationResult,
  TestTelegramResult,
  AutoSetupOidcPayload,
  AutoSetupOidcResult
} from '../types';

const API_BASE = '/api';

export const api = {
  async getHealth(): Promise<HealthStatus> {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) throw new Error('Failed to fetch health');
    return res.json();
  },

  async getAuthStatus(): Promise<AuthStatus> {
    const res = await fetch(`${API_BASE}/auth/status`);
    if (!res.ok) throw new Error('Failed to fetch auth status');
    return res.json();
  },

  async loginPassword(password: string): Promise<{ status: string; token: string }> {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Login failed' }));
      throw new Error(err.detail || 'Login failed');
    }
    return res.json();
  },

  async logout(): Promise<void> {
    await fetch(`${API_BASE}/auth/logout`, { method: 'POST' });
  },

  async getMatrix(): Promise<AccessMatrixData> {
    const res = await fetch(`${API_BASE}/matrix`);
    if (!res.ok) throw new Error('Failed to fetch access matrix');
    return res.json();
  },

  async togglePermission(user_pk: number, app_pk: string, group_pk: string, grant: boolean): Promise<void> {
    const res = await fetch(`${API_BASE}/matrix/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_pk, app_pk, group_pk, grant }),
    });
    if (!res.ok) throw new Error('Failed to update permission');
  },

  async bulkTogglePermissions(changes: StagedChange[]): Promise<{ succeeded: number; failed: number; total: number }> {
    const payload = {
      changes: changes.map((c) => ({
        user_pk: c.user_pk,
        app_pk: c.app_pk,
        group_pk: c.group_pk,
        grant: c.grant,
      })),
    };
    const res = await fetch(`${API_BASE}/matrix/bulk-toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('Failed to apply bulk changes');
    return res.json();
  },

  async provisionApp(
    app_pk: string,
    options?: {
      group_name?: string;
      create_user_group?: boolean;
      create_admin_group?: boolean;
      custom_user_group_name?: string;
      custom_admin_group_name?: string;
    }
  ): Promise<any> {
    const res = await fetch(`${API_BASE}/apps/provision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        app_pk,
        group_name: options?.group_name,
        create_user_group: options?.create_user_group ?? true,
        create_admin_group: options?.create_admin_group ?? true,
        custom_user_group_name: options?.custom_user_group_name,
        custom_admin_group_name: options?.custom_admin_group_name,
      }),
    });
    if (!res.ok) throw new Error('Failed to provision app group');
    return res.json();
  },

  async provisionAll(options?: {
    create_user_groups?: boolean;
    create_admin_groups?: boolean;
    include_already_secured?: boolean;
  }): Promise<{ provisioned_count: number; provisioned_apps: string[] }> {
    const res = await fetch(`${API_BASE}/apps/provision-all`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        create_user_groups: options?.create_user_groups ?? true,
        create_admin_groups: options?.create_admin_groups ?? true,
        include_already_secured: options?.include_already_secured ?? true,
      }),
    });
    if (!res.ok) throw new Error('Failed to provision apps');
    return res.json();
  },

  async provisionAllUnprotected(): Promise<{ provisioned_count: number; provisioned_apps: string[] }> {
    return this.provisionAll({ include_already_secured: true });
  },

  async toggleUserActive(user_pk: number): Promise<{ is_active: boolean }> {
    const res = await fetch(`${API_BASE}/users/${user_pk}/toggle-active`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to toggle user active state');
    return res.json();
  },

  async getInvites(): Promise<TrackedInvite[]> {
    const res = await fetch(`${API_BASE}/invites`);
    if (!res.ok) throw new Error('Failed to fetch invites');
    return res.json();
  },

  async createInvite(params: {
    name: string;
    email?: string;
    phone?: string;
    send_via_whatsapp?: boolean;
    custom_message?: string;
    expires_in_days: number;
    single_use: boolean;
    group_pks: string[];
    app_names: string[];
  }): Promise<TrackedInvite> {
    const res = await fetch(`${API_BASE}/invites`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to create invite' }));
      throw new Error(err.detail || 'Failed to create invite');
    }
    return res.json();
  },

  async revokeInvite(invitation_pk: string): Promise<void> {
    const res = await fetch(`${API_BASE}/invites/${invitation_pk}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to revoke invite');
  },

  async getWhatsAppStatus(): Promise<any> {
    const res = await fetch(`${API_BASE}/whatsapp/status`);
    if (!res.ok) throw new Error('Failed to fetch WhatsApp status');
    return res.json();
  },

  async sendWhatsAppMessage(recipient: string, message: string): Promise<any> {
    const res = await fetch(`${API_BASE}/whatsapp/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recipient, message }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to send WhatsApp message' }));
      throw new Error(err.detail || 'Failed to send WhatsApp message');
    }
    return res.json();
  },

  async logoutWhatsApp(): Promise<any> {
    const res = await fetch(`${API_BASE}/whatsapp/logout`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to disconnect WhatsApp');
    return res.json();
  },

  async getExpressionPolicySnippet(): Promise<{ title: string; description: string; snippet: string }> {
    const res = await fetch(`${API_BASE}/invites/expression-policy`);
    if (!res.ok) throw new Error('Failed to fetch expression policy');
    return res.json();
  },

  async installFlowPolicy(): Promise<{ status: string; message: string }> {
    const res = await fetch(`${API_BASE}/invites/install-policy`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to install policy' }));
      throw new Error(err.detail || 'Failed to install policy');
    }
    return res.json();
  },

  async syncInvites(): Promise<{ status: string; redeemed_count: number }> {
    const res = await fetch(`${API_BASE}/invites/sync`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to sync invitations');
    return res.json();
  },

  async getAuditLogs(limit: number = 100): Promise<AuditLog[]> {
    const res = await fetch(`${API_BASE}/audit?limit=${limit}`);
    if (!res.ok) throw new Error('Failed to fetch audit logs');
    return res.json();
  },

  async createLease(params: {
    user_pk: number;
    user_name: string;
    app_pk: string;
    app_name: string;
    group_pk: string;
    role: 'member' | 'admin';
    duration_hours?: number;
    expires_at?: string;
  }): Promise<ExpiringGrant> {
    const res = await fetch(`${API_BASE}/matrix/lease`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) throw new Error('Failed to create temporary access grant');
    return res.json();
  },

  async revokeLease(user_pk: number, app_pk: string, group_pk: string): Promise<void> {
    const res = await fetch(`${API_BASE}/matrix/lease`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_pk, app_pk, group_pk }),
    });
    if (!res.ok) throw new Error('Failed to revoke temporary lease');
  },

  async getTemplates(): Promise<AccessTemplate[]> {
    const res = await fetch(`${API_BASE}/templates`);
    if (!res.ok) throw new Error('Failed to fetch access templates');
    return res.json();
  },

  async createTemplate(params: {
    name: string;
    description?: string;
    icon?: string;
    assignments: Record<string, string>;
  }): Promise<AccessTemplate> {
    const res = await fetch(`${API_BASE}/templates`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) throw new Error('Failed to create access template');
    return res.json();
  },

  async deleteTemplate(templateId: number): Promise<void> {
    const res = await fetch(`${API_BASE}/templates/${templateId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete access template');
  },

  async applyTemplate(templateId: number, params: {
    user_pk: number;
    user_name: string;
    duration_hours?: number;
  }): Promise<any> {
    const res = await fetch(`${API_BASE}/templates/${templateId}/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) throw new Error('Failed to apply access template');
    return res.json();
  },

  async getSettings(): Promise<AppSettings> {
    const res = await fetch(`${API_BASE}/settings`);
    if (!res.ok) throw new Error('Failed to fetch settings');
    return res.json();
  },

  async updateSettings(payload: UpdateSettingsPayload): Promise<AppSettings> {
    const res = await fetch(`${API_BASE}/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to update settings' }));
      throw new Error(err.detail || 'Failed to update settings');
    }
    return res.json();
  },

  async testAuthentikConnection(params: {
    url?: string;
    token?: string;
    insecure_skip_verify?: boolean;
  }): Promise<TestConnectionResult> {
    const res = await fetch(`${API_BASE}/settings/test-authentik`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) throw new Error('Failed to test Authentik connection');
    return res.json();
  },

  async testNotification(channel: string = 'all'): Promise<TestNotificationResult> {
    const res = await fetch(`${API_BASE}/settings/test-notification`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channel }),
    });
    if (!res.ok) throw new Error('Failed to dispatch test notification');
    return res.json();
  },

  async testTelegram(token?: string): Promise<TestTelegramResult> {
    const res = await fetch(`${API_BASE}/settings/test-telegram`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });
    if (!res.ok) throw new Error('Failed to test Telegram bot connection');
    return res.json();
  },

  async autoSetupOidc(payload: AutoSetupOidcPayload): Promise<AutoSetupOidcResult> {
    const res = await fetch(`${API_BASE}/settings/auto-setup-oidc`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to configure OIDC in Authentik' }));
      let detailMsg = 'Failed to configure OIDC in Authentik';
      let errorLogs: string[] = [];
      if (typeof err.detail === 'object' && err.detail !== null) {
        detailMsg = err.detail.error || err.detail.message || JSON.stringify(err.detail);
        errorLogs = err.detail.logs || [];
      } else if (typeof err.detail === 'string') {
        detailMsg = err.detail;
      }
      const errorObj: any = new Error(detailMsg);
      errorObj.logs = errorLogs;
      throw errorObj;
    }
    return res.json();
  },

  async detectUrl(): Promise<{ detected_url: string; saved_url: string; redirect_uri: string }> {
    const res = await fetch(`${API_BASE}/settings/detect-url`);
    if (!res.ok) throw new Error('Failed to detect URL');
    return res.json();
  },

  async exportMatrixCsv(): Promise<void> {
    const res = await fetch(`${API_BASE}/matrix/export/csv`);
    if (!res.ok) throw new Error('Failed to export matrix CSV');
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `authentik_matrix_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  },

  async updateUserPhone(user_pk: number, phone: string): Promise<{ user_pk: number; phone: string }> {
    const res = await fetch(`${API_BASE}/users/${user_pk}/phone`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to update phone number' }));
      throw new Error(err.detail || 'Failed to update phone number');
    }
    return res.json();
  },

  async ensurePhoneScope(): Promise<{ status: string; mapping: any }> {
    const res = await fetch(`${API_BASE}/settings/ensure-phone-scope`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) throw new Error('Failed to ensure phone scope mapping in Authentik');
    return res.json();
  },
};
