import React, { useState, useEffect } from 'react';
import { 
  Key, 
  Globe, 
  MessageSquare, 
  Save, 
  Clock, 
  Bell, 
  Eye, 
  EyeOff, 
  Activity,
  CheckCircle2,
  XCircle,
  HelpCircle
} from 'lucide-react';
import { api } from '../api/client';
import { UpdateSettingsPayload } from '../types';

interface SettingsPanelProps {
  onShowToast: (message: string, type?: 'success' | 'error' | 'info') => void;
  onSettingsUpdated?: () => void;
}

export const SettingsPanel: React.FC<SettingsPanelProps> = ({
  onShowToast,
  onSettingsUpdated,
}) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; error?: string } | null>(null);

  // Form Fields
  const [authentikUrl, setAuthentikUrl] = useState('');
  const [authentikToken, setAuthentikToken] = useState('');
  const [showToken, setShowToken] = useState(false);
  const [tokenMasked, setTokenMasked] = useState('');
  const [tokenConfigured, setTokenConfigured] = useState(false);
  const [insecureSkipVerify, setInsecureSkipVerify] = useState(false);
  const [appGroupPrefix, setAppGroupPrefix] = useState('App - ');
  const [enrollmentFlow, setEnrollmentFlow] = useState('default-enrollment-flow');

  const [whatsappEnabled, setWhatsappEnabled] = useState(true);
  const [whatsappServiceUrl, setWhatsappServiceUrl] = useState('http://127.0.0.1:3001');
  const [defaultCountryCode, setDefaultCountryCode] = useState('44');
  const [customInviteMessage, setCustomInviteMessage] = useState('');
  const [webhookUrl, setWebhookUrl] = useState('');

  const [defaultLeaseHours, setDefaultLeaseHours] = useState(72);
  const [defaultInviteDays, setDefaultInviteDays] = useState(7);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    setLoading(true);
    try {
      const s = await api.getSettings();
      setAuthentikUrl(s.authentik_url || '');
      setTokenMasked(s.authentik_token_masked || '');
      setTokenConfigured(s.authentik_token_configured);
      setInsecureSkipVerify(s.authentik_insecure_skip_verify);
      setAppGroupPrefix(s.app_group_prefix || 'App - ');
      setEnrollmentFlow(s.default_enrollment_flow || 'default-enrollment-flow');

      setWhatsappEnabled(s.whatsapp_enabled);
      setWhatsappServiceUrl(s.whatsapp_service_url || 'http://127.0.0.1:3001');
      setDefaultCountryCode(s.default_country_code || '44');
      setCustomInviteMessage(s.custom_invite_message || '');
      setWebhookUrl(s.notification_webhook_url || '');

      setDefaultLeaseHours(s.default_lease_duration_hours || 72);
      setDefaultInviteDays(s.default_invite_expiry_days || 7);
    } catch (err: any) {
      onShowToast(err.message || 'Failed to load settings', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleTestConnection = async () => {
    setTestingConnection(true);
    setTestResult(null);
    try {
      const res = await api.testAuthentikConnection({
        url: authentikUrl,
        token: authentikToken || undefined,
        insecure_skip_verify: insecureSkipVerify,
      });
      if (res.success) {
        setTestResult({ success: true });
        onShowToast('Successfully connected to Authentik API!', 'success');
      } else {
        setTestResult({ success: false, error: res.error || 'Connection failed' });
        onShowToast('Authentik connection failed', 'error');
      }
    } catch (err: any) {
      setTestResult({ success: false, error: err.message || 'Network request failed' });
      onShowToast('Failed to execute connection test', 'error');
    } finally {
      setTestingConnection(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload: UpdateSettingsPayload = {
        authentik_url: authentikUrl,
        authentik_insecure_skip_verify: insecureSkipVerify,
        app_group_prefix: appGroupPrefix,
        default_enrollment_flow: enrollmentFlow,
        whatsapp_enabled: whatsappEnabled,
        whatsapp_service_url: whatsappServiceUrl,
        default_country_code: defaultCountryCode,
        custom_invite_message: customInviteMessage || null,
        notification_webhook_url: webhookUrl || null,
        default_lease_duration_hours: Number(defaultLeaseHours),
        default_invite_expiry_days: Number(defaultInviteDays),
      };

      // Only include token if user entered a new one
      if (authentikToken.trim()) {
        payload.authentik_token = authentikToken.trim();
      }

      const updated = await api.updateSettings(payload);
      setTokenMasked(updated.authentik_token_masked);
      setTokenConfigured(updated.authentik_token_configured);
      setAuthentikToken(''); // Clear input after saving
      onShowToast('Settings updated successfully and saved to encrypted database!', 'success');
      if (onSettingsUpdated) onSettingsUpdated();
    } catch (err: any) {
      onShowToast(err.message || 'Failed to save settings', 'error');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-[#111827] border border-[#25354b] rounded-2xl p-12 text-center shadow-xl">
        <Activity className="h-8 w-8 text-[#fd7e14] animate-spin mx-auto mb-3" />
        <p className="text-xs text-slate-400">Loading system settings from database...</p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSave} className="space-y-6">
      
      {/* Page Title & Overview */}
      <div className="bg-[#111827] border border-[#25354b] rounded-2xl p-6 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2.5">
            <div className="h-8 w-8 rounded-lg bg-orange-500/15 text-[#fd7e14] border border-orange-500/30 flex items-center justify-center">
              <Key className="h-4 w-4" />
            </div>
            <h2 className="text-lg font-bold text-white tracking-tight">System & API Administration</h2>
          </div>
          <p className="text-xs text-slate-400 mt-1 max-w-2xl">
            Configure your Authentik connection, WhatsApp bridge, and automation policies. All sensitive credentials are encrypted with AES Fernet and stored in your local SQLite database.
          </p>
        </div>

        <button
          type="submit"
          disabled={saving}
          className="flex items-center justify-center space-x-2 bg-[#fd7e14] hover:bg-[#ea6c0a] disabled:opacity-50 text-white text-xs font-semibold px-4 py-2.5 rounded-xl shadow-md transition-colors shrink-0"
        >
          <Save className="h-4 w-4" />
          <span>{saving ? 'Saving...' : 'Save Settings'}</span>
        </button>
      </div>

      {/* Grid of Setting Sections */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* 1. Authentik Connection Settings */}
        <div className="bg-[#111827] border border-[#25354b] rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-[#25354b]">
            <div className="flex items-center space-x-2">
              <Globe className="h-4 w-4 text-[#fd7e14]" />
              <h3 className="text-sm font-bold text-white">Authentik API Connection</h3>
            </div>
            <span className="text-[10px] text-emerald-400 font-mono bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
              Encrypted Storage
            </span>
          </div>

          {/* Authentik URL */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-300">Authentik Instance URL</label>
            <input
              type="url"
              required
              value={authentikUrl}
              onChange={(e) => setAuthentikUrl(e.target.value)}
              placeholder="https://auth.company.com"
              className="w-full bg-[#0b0f17] border border-[#25354b] rounded-xl px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-[#fd7e14]"
            />
            <p className="text-[10px] text-slate-500">Base URL where your Authentik server is hosted.</p>
          </div>

          {/* Authentik API Token */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-slate-300">API Bearer Token</label>
              {tokenConfigured && (
                <span className="text-[10px] text-slate-400 font-mono">
                  Current: {tokenMasked}
                </span>
              )}
            </div>
            <div className="relative">
              <input
                type={showToken ? 'text' : 'password'}
                value={authentikToken}
                onChange={(e) => setAuthentikToken(e.target.value)}
                placeholder={tokenConfigured ? 'Enter new token to replace existing...' : 'Paste Authentik API token...'}
                className="w-full bg-[#0b0f17] border border-[#25354b] rounded-xl pl-3.5 pr-10 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-[#fd7e14] font-mono"
              />
              <button
                type="button"
                onClick={() => setShowToken(!showToken)}
                className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-200"
              >
                {showToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            <p className="text-[10px] text-slate-500">
              Generate in Authentik: Directory → Users → [Your Admin] → Service-Accounts / Tokens.
            </p>
          </div>

          {/* Skip SSL Verify */}
          <div className="pt-1">
            <label className="flex items-center space-x-2.5 cursor-pointer">
              <input
                type="checkbox"
                checked={insecureSkipVerify}
                onChange={(e) => setInsecureSkipVerify(e.target.checked)}
                className="rounded border-[#25354b] bg-[#0b0f17] text-[#fd7e14] focus:ring-[#fd7e14] h-4 w-4"
              />
              <div>
                <span className="text-xs font-medium text-slate-200">Skip SSL / TLS Verification</span>
                <p className="text-[10px] text-slate-500">Enable if using self-signed internal certificates.</p>
              </div>
            </label>
          </div>

          {/* Test Connection Button & Result */}
          <div className="pt-2">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={handleTestConnection}
                disabled={testingConnection}
                className="flex items-center space-x-1.5 bg-[#16202e] hover:bg-[#1e2c3f] border border-[#25354b] text-slate-200 text-xs px-3 py-1.5 rounded-lg transition-colors"
              >
                <Activity className={`h-3.5 w-3.5 ${testingConnection ? 'animate-spin text-[#fd7e14]' : 'text-slate-400'}`} />
                <span>{testingConnection ? 'Testing...' : 'Test Connection'}</span>
              </button>

              {testResult && (
                <div className={`flex items-center gap-1.5 text-xs ${testResult.success ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {testResult.success ? (
                    <>
                      <CheckCircle2 className="h-4 w-4 shrink-0" />
                      <span>Connected successfully!</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="h-4 w-4 shrink-0" />
                      <span className="truncate max-w-[220px]" title={testResult.error}>
                        {testResult.error}
                      </span>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Advanced RBAC Parameters */}
          <div className="pt-2 border-t border-[#25354b] space-y-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-300">App Group Prefix</label>
              <input
                type="text"
                value={appGroupPrefix}
                onChange={(e) => setAppGroupPrefix(e.target.value)}
                placeholder="App - "
                className="w-full bg-[#0b0f17] border border-[#25354b] rounded-xl px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-[#fd7e14]"
              />
              <p className="text-[10px] text-slate-500">Naming convention for per-service groups (e.g. "App - Bookstack").</p>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-300">Default Enrollment Flow Slug</label>
              <input
                type="text"
                value={enrollmentFlow}
                onChange={(e) => setEnrollmentFlow(e.target.value)}
                placeholder="default-enrollment-flow"
                className="w-full bg-[#0b0f17] border border-[#25354b] rounded-xl px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-[#fd7e14]"
              />
              <p className="text-[10px] text-slate-500">Authentik Flow used when new invited users accept invitations.</p>
            </div>
          </div>

        </div>

        {/* 2. Notifications & Messaging */}
        <div className="bg-[#111827] border border-[#25354b] rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-[#25354b]">
            <div className="flex items-center space-x-2">
              <MessageSquare className="h-4 w-4 text-emerald-400" />
              <h3 className="text-sm font-bold text-white">Notifications & WhatsApp</h3>
            </div>
          </div>

          {/* WhatsApp Enabled Toggle */}
          <div className="pt-1">
            <label className="flex items-center space-x-2.5 cursor-pointer">
              <input
                type="checkbox"
                checked={whatsappEnabled}
                onChange={(e) => setWhatsappEnabled(e.target.checked)}
                className="rounded border-[#25354b] bg-[#0b0f17] text-[#fd7e14] focus:ring-[#fd7e14] h-4 w-4"
              />
              <div>
                <span className="text-xs font-medium text-slate-200">Enable WhatsApp Bridge</span>
                <p className="text-[10px] text-slate-500">Dispatch invitation links directly via paired WhatsApp.</p>
              </div>
            </label>
          </div>

          {/* WhatsApp Microservice URL */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-300">WhatsApp Bridge Service URL</label>
            <input
              type="text"
              value={whatsappServiceUrl}
              onChange={(e) => setWhatsappServiceUrl(e.target.value)}
              placeholder="http://127.0.0.1:3001"
              className="w-full bg-[#0b0f17] border border-[#25354b] rounded-xl px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-[#fd7e14]"
            />
            <p className="text-[10px] text-slate-500">Internal address of the Baileys headless bridge container.</p>
          </div>

          {/* Default Country Code */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-300">Default Phone Country Code</label>
            <div className="relative">
              <span className="absolute left-3.5 top-2 text-slate-400 text-xs font-mono">+</span>
              <input
                type="text"
                value={defaultCountryCode}
                onChange={(e) => setDefaultCountryCode(e.target.value.replace(/\D/, ''))}
                placeholder="44"
                className="w-full bg-[#0b0f17] border border-[#25354b] rounded-xl pl-8 pr-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-[#fd7e14] font-mono"
              />
            </div>
            <p className="text-[10px] text-slate-500">Auto-prefixed to phone numbers without international code.</p>
          </div>

          {/* Custom Invite Template */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-300">Custom Invitation Message Template</label>
            <textarea
              rows={3}
              value={customInviteMessage}
              onChange={(e) => setCustomInviteMessage(e.target.value)}
              placeholder="Hi {name}! You have been invited to access our home services. Claim your account here: {url}"
              className="w-full bg-[#0b0f17] border border-[#25354b] rounded-xl px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-[#fd7e14] font-sans"
            />
            <p className="text-[10px] text-slate-500">
              Variables: <code className="text-orange-300">{'{name}'}</code>, <code className="text-orange-300">{'{url}'}</code>, <code className="text-orange-300">{'{expires}'}</code>
            </p>
          </div>

          {/* Notification Webhook */}
          <div className="space-y-1.5 pt-2 border-t border-[#25354b]">
            <div className="flex items-center space-x-1.5">
              <Bell className="h-3.5 w-3.5 text-amber-400" />
              <label className="text-xs font-medium text-slate-300">Security & Expiry Webhook URL (Optional)</label>
            </div>
            <input
              type="url"
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
              placeholder="https://discord.com/api/webhooks/... or https://hooks.slack.com/..."
              className="w-full bg-[#0b0f17] border border-[#25354b] rounded-xl px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-[#fd7e14]"
            />
            <p className="text-[10px] text-slate-500">Sends alerts when guest passes expire or invites are redeemed.</p>
          </div>

        </div>

        {/* 3. Automation & Policy Defaults */}
        <div className="bg-[#111827] border border-[#25354b] rounded-2xl p-6 shadow-xl space-y-4 lg:col-span-2">
          <div className="flex items-center justify-between pb-3 border-b border-[#25354b]">
            <div className="flex items-center space-x-2">
              <Clock className="h-4 w-4 text-amber-400" />
              <h3 className="text-sm font-bold text-white">Automation & Policy Defaults</h3>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Default Lease Duration */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-300">Default Temporary Guest Pass Duration</label>
              <select
                value={defaultLeaseHours}
                onChange={(e) => setDefaultLeaseHours(Number(e.target.value))}
                className="w-full bg-[#0b0f17] border border-[#25354b] rounded-xl px-3.5 py-2 text-xs text-slate-100 focus:outline-none focus:border-[#fd7e14]"
              >
                <option value={24}>24 Hours (1 Day)</option>
                <option value={72}>72 Hours (3 Days - Default)</option>
                <option value={168}>7 Days (1 Week)</option>
                <option value={720}>30 Days (1 Month)</option>
              </select>
              <p className="text-[10px] text-slate-500">Pre-selected expiration duration when creating guest passes.</p>
            </div>

            {/* Default Invite Expiry */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-300">Default Invitation Link Validity</label>
              <select
                value={defaultInviteDays}
                onChange={(e) => setDefaultInviteDays(Number(e.target.value))}
                className="w-full bg-[#0b0f17] border border-[#25354b] rounded-xl px-3.5 py-2 text-xs text-slate-100 focus:outline-none focus:border-[#fd7e14]"
              >
                <option value={1}>24 Hours</option>
                <option value={3}>3 Days</option>
                <option value={7}>7 Days (Default)</option>
                <option value={14}>14 Days</option>
                <option value={30}>30 Days</option>
              </select>
              <p className="text-[10px] text-slate-500">Days before unredeemed invitation tokens expire in Authentik.</p>
            </div>
          </div>

          {/* Security Notice Note */}
          <div className="mt-4 p-3 rounded-xl bg-[#16202e] border border-[#25354b] text-[11px] text-slate-400 flex items-start gap-2.5">
            <HelpCircle className="h-4 w-4 text-sky-400 shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold text-slate-200">Where are authentication settings managed?</span>
              <p className="mt-0.5">
                Authentication mechanisms (<code className="text-orange-300 font-mono">AUTH_METHOD</code>, <code className="text-orange-300 font-mono">ADMIN_PASSWORD</code>, and OIDC client secrets) remain anchored in your server's <code className="text-orange-300 font-mono">.env</code> file for zero-trust bootstrapping security.
              </p>
            </div>
          </div>

        </div>

      </div>

      {/* Save Button Bar */}
      <div className="flex justify-end">
        <button
          type="submit"
          disabled={saving}
          className="flex items-center space-x-2 bg-[#fd7e14] hover:bg-[#ea6c0a] disabled:opacity-50 text-white text-xs font-semibold px-6 py-2.5 rounded-xl shadow-md transition-colors"
        >
          <Save className="h-4 w-4" />
          <span>{saving ? 'Saving Changes...' : 'Save All Settings'}</span>
        </button>
      </div>

    </form>
  );
};
