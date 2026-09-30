import React, { useState, useEffect } from 'react';
import { 
  ShieldCheck, 
  Globe, 
  Lock, 
  Users, 
  CheckCircle2, 
  AlertCircle, 
  RefreshCw, 
  ExternalLink,
  X,
  Sparkles
} from 'lucide-react';
import { api } from '../api/client';
import { AutoSetupOidcResult } from '../types';

interface OidcSetupModalProps {
  isOpen: boolean;
  onClose: () => void;
  onShowToast: (message: string, type?: 'success' | 'error' | 'info') => void;
  onSuccess?: () => void;
}

export const OidcSetupModal: React.FC<OidcSetupModalProps> = ({
  isOpen,
  onClose,
  onShowToast,
  onSuccess,
}) => {
  const [appUrl, setAppUrl] = useState('');
  const [appName, setAppName] = useState('Authentik Access Manager');
  const [appSlug, setAppSlug] = useState('authentik-manager');
  const [adminGroupName, setAdminGroupName] = useState('authentik Admins');
  const [activateImmediately, setActivateImmediately] = useState(true);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AutoSetupOidcResult | null>(null);

  // Auto-detect URL on open
  useEffect(() => {
    if (isOpen) {
      setError(null);
      setResult(null);
      
      // Browser origin is immediate and reliable
      const browserOrigin = window.location.origin;
      setAppUrl(browserOrigin);

      // Also check if backend already has a saved app_url
      api.detectUrl().then((res) => {
        if (res.saved_url && res.saved_url !== 'http://localhost:8000') {
          setAppUrl(res.saved_url);
        } else if (browserOrigin) {
          setAppUrl(browserOrigin);
        }
      }).catch(() => {});
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleUseBrowserOrigin = () => {
    setAppUrl(window.location.origin);
    onShowToast(`Applied current browser URL: ${window.location.origin}`, 'info');
  };

  const handleExecuteSetup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!appUrl) {
      setError('Application URL is required for OAuth callback generation.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await api.autoSetupOidc({
        app_url: appUrl,
        app_name: appName,
        app_slug: appSlug,
        admin_group_name: adminGroupName,
        activate_immediately: activateImmediately,
      });
      setResult(res);
      onShowToast('Authentik OIDC / SSO configured successfully!', 'success');
      if (onSuccess) onSuccess();
    } catch (err: any) {
      setError(err.message || 'Failed to automate OIDC setup in Authentik');
    } finally {
      setLoading(false);
    }
  };

  const redirectUri = `${appUrl.replace(/\/+$/, '')}/api/auth/oidc/callback`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-[#111827] border border-[#25354b] rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh]">
        
        {/* Header */}
        <div className="px-6 py-5 border-b border-[#25354b] flex items-center justify-between bg-[#151e2e]/50">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-orange-500/20 to-amber-500/10 border border-orange-500/30 flex items-center justify-center text-[#fd7e14] shadow-sm">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                Automate Authentik OIDC / SSO Setup
                <span className="text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full bg-orange-500/20 text-orange-300 border border-orange-500/30">
                  1-Click Automation
                </span>
              </h3>
              <p className="text-xs text-slate-400">
                Create provider, register application, and bind admin permissions via Authentik API
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body Content */}
        <div className="p-6 overflow-y-auto space-y-6 text-xs text-slate-300">
          
          {/* Success Result View */}
          {result ? (
            <div className="space-y-5 animate-in fade-in duration-300">
              <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/25 flex items-start gap-3">
                <CheckCircle2 className="h-6 w-6 text-emerald-400 shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <h4 className="text-sm font-bold text-emerald-200">
                    OIDC Single Sign-On Configured & Secured!
                  </h4>
                  <p className="text-xs text-emerald-300/80">
                    Authentik Access Manager is now officially registered in Authentik. Only members of the <strong className="text-emerald-200">'{result.bound_group_name}'</strong> group will be permitted to access this manager.
                  </p>
                </div>
              </div>

              {/* Steps Completed Checklist */}
              <div className="bg-[#0b0f17] border border-[#25354b] rounded-xl p-4 space-y-2.5">
                <div className="font-semibold text-slate-200 text-xs uppercase tracking-wider text-[11px] mb-2 flex items-center gap-1.5">
                  <ShieldCheck className="h-4 w-4 text-emerald-400" />
                  Completed Provisioning Steps
                </div>
                {result.steps_completed.map((step, idx) => (
                  <div key={idx} className="flex items-center gap-2 text-slate-300 text-xs">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                    <span>{step}</span>
                  </div>
                ))}
              </div>

              {/* Provisioned Details Summary */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div className="bg-[#0b0f17] border border-[#25354b] rounded-xl p-3">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Client ID</div>
                  <div className="font-mono text-slate-200 text-[11px] mt-0.5 truncate select-all">{result.client_id}</div>
                </div>
                <div className="bg-[#0b0f17] border border-[#25354b] rounded-xl p-3">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Application Slug</div>
                  <div className="font-mono text-slate-200 text-[11px] mt-0.5">{result.application_slug}</div>
                </div>
                <div className="bg-[#0b0f17] border border-[#25354b] rounded-xl p-3">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Redirect URI</div>
                  <div className="font-mono text-slate-200 text-[11px] mt-0.5 truncate select-all">{result.redirect_uri}</div>
                </div>
                <div className="bg-[#0b0f17] border border-[#25354b] rounded-xl p-3">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Issuer URL</div>
                  <div className="font-mono text-slate-200 text-[11px] mt-0.5 truncate select-all">{result.issuer_url}</div>
                </div>
              </div>

              <div className="pt-3 flex items-center justify-between border-t border-[#25354b]">
                <a
                  href="/api/auth/oidc/login"
                  target="_blank"
                  rel="noreferrer"
                  className="px-4 py-2.5 rounded-xl bg-orange-500/20 hover:bg-orange-500/30 text-orange-200 border border-orange-500/40 text-xs font-semibold flex items-center gap-1.5 transition-colors"
                >
                  <ExternalLink className="h-4 w-4" />
                  Test Authentik OIDC Login (New Tab)
                </a>

                <button
                  type="button"
                  onClick={() => {
                    onClose();
                    window.location.reload();
                  }}
                  className="px-5 py-2.5 rounded-xl bg-[#fd7e14] hover:bg-[#ea6c0a] text-white text-xs font-semibold transition-colors shadow"
                >
                  Done & Reload Dashboard
                </button>
              </div>
            </div>
          ) : (
            /* Setup Wizard Form */
            <form onSubmit={handleExecuteSetup} className="space-y-5">
              {error && (
                <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-start gap-2.5">
                  <AlertCircle className="h-4 w-4 text-rose-400 shrink-0 mt-0.5" />
                  <div>
                    <div className="font-semibold text-rose-200">Configuration Error</div>
                    <div className="text-[11px] mt-0.5">{error}</div>
                  </div>
                </div>
              )}

              {/* Step 1: Detect Application URL */}
              <div className="bg-[#0b0f17] border border-[#25354b] rounded-xl p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <label className="font-semibold text-white flex items-center gap-2">
                    <Globe className="h-4 w-4 text-orange-400" />
                    Manager Application URL (Base Host)
                  </label>
                  <button
                    type="button"
                    onClick={handleUseBrowserOrigin}
                    className="text-[11px] text-orange-400 hover:text-orange-300 bg-orange-500/10 hover:bg-orange-500/20 border border-orange-500/25 px-2 py-0.5 rounded-md flex items-center gap-1 transition-colors"
                  >
                    <RefreshCw className="h-3 w-3" />
                    Use Current Browser URL
                  </button>
                </div>
                <p className="text-[11px] text-slate-400">
                  The URL where users and Authentik will reach this dashboard. Used to register Authentik's authorized redirect URI.
                </p>
                <input
                  type="text"
                  value={appUrl}
                  onChange={(e) => setAppUrl(e.target.value)}
                  placeholder="https://manager.homelab.lan"
                  className="w-full bg-[#111827] border border-[#25354b] rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-[#fd7e14] font-mono"
                  required
                />
                <div className="text-[11px] text-slate-400 flex items-center gap-1.5 pt-1">
                  <span className="text-slate-500">Calculated Redirect URI:</span>
                  <span className="font-mono text-orange-300 bg-[#111827] px-2 py-0.5 rounded border border-[#25354b]">
                    {redirectUri}
                  </span>
                </div>
              </div>

              {/* Step 2: Authentik Configuration Settings */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="font-semibold text-white text-xs">Application Name</label>
                  <input
                    type="text"
                    value={appName}
                    onChange={(e) => setAppName(e.target.value)}
                    className="w-full bg-[#0b0f17] border border-[#25354b] rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-[#fd7e14]"
                    required
                  />
                  <p className="text-[11px] text-slate-500">Display name inside Authentik's App Portal</p>
                </div>

                <div className="space-y-1.5">
                  <label className="font-semibold text-white text-xs">Application Slug</label>
                  <input
                    type="text"
                    value={appSlug}
                    onChange={(e) => setAppSlug(e.target.value)}
                    className="w-full bg-[#0b0f17] border border-[#25354b] rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-[#fd7e14] font-mono"
                    required
                  />
                  <p className="text-[11px] text-slate-500">Unique URL slug (e.g. authentik-manager)</p>
                </div>
              </div>

              {/* Step 3: Admin Group Access Restriction */}
              <div className="bg-[#0b0f17] border border-[#25354b] rounded-xl p-4 space-y-2.5">
                <label className="font-semibold text-white flex items-center gap-2">
                  <Users className="h-4 w-4 text-sky-400" />
                  Access Restriction Group (RBAC)
                </label>
                <p className="text-[11px] text-slate-400">
                  Only members of this group in Authentik will be granted permission to log in and manage permissions.
                </p>
                <input
                  type="text"
                  value={adminGroupName}
                  onChange={(e) => setAdminGroupName(e.target.value)}
                  placeholder="authentik Admins"
                  className="w-full bg-[#111827] border border-[#25354b] rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-[#fd7e14]"
                  required
                />
              </div>

              {/* Step 4: Immediate Activation Toggle */}
              <div className="p-3.5 rounded-xl bg-orange-500/5 border border-orange-500/20 flex items-center justify-between">
                <div className="space-y-0.5">
                  <div className="font-semibold text-white text-xs flex items-center gap-1.5">
                    <Lock className="h-3.5 w-3.5 text-orange-400" />
                    Activate OIDC Login Immediately
                  </div>
                  <p className="text-[11px] text-slate-400">
                    Switches active auth method to OIDC upon successful provisioning.
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={activateImmediately}
                  onChange={(e) => setActivateImmediately(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-700 bg-slate-900 text-orange-500 focus:ring-0 focus:ring-offset-0 cursor-pointer"
                />
              </div>

              {/* Submit Buttons */}
              <div className="pt-3 flex items-center justify-end gap-3 border-t border-[#25354b]">
                <button
                  type="button"
                  onClick={onClose}
                  disabled={loading}
                  className="px-4 py-2.5 rounded-xl border border-[#25354b] text-slate-300 hover:text-white hover:bg-slate-800 text-xs font-semibold transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="px-5 py-2.5 rounded-xl bg-[#fd7e14] hover:bg-[#ea6c0a] disabled:opacity-50 text-white text-xs font-semibold flex items-center gap-2 transition-all shadow hover:shadow-orange-500/20 cursor-pointer"
                >
                  {loading ? (
                    <>
                      <RefreshCw className="h-4 w-4 animate-spin" />
                      Provisioning in Authentik...
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-4 w-4" />
                      🚀 Configure in Authentik & Enable SSO
                    </>
                  )}
                </button>
              </div>
            </form>
          )}

        </div>
      </div>
    </div>
  );
};
