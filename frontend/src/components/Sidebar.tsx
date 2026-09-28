import React, { useState } from 'react';
import { 
  Shield, 
  RefreshCw, 
  UserPlus, 
  Layers, 
  FileText, 
  BookOpen, 
  LogOut, 
  LogIn,
  MessageSquare,
  Sparkles,
  Settings,
  Menu,
  X
} from 'lucide-react';
import { HealthStatus, AuthStatus, WhatsAppStatus } from '../types';

interface SidebarProps {
  health: HealthStatus | null;
  auth: AuthStatus | null;
  whatsAppStatus: WhatsAppStatus | null;
  activeTab: 'matrix' | 'invites' | 'audit' | 'settings';
  setActiveTab: (tab: 'matrix' | 'invites' | 'audit' | 'settings') => void;
  stagedMode: boolean;
  setStagedMode: (val: boolean) => void;
  onRefresh: () => void;
  onOpenInviteModal: () => void;
  onOpenGuideModal: () => void;
  onOpenWhatsAppModal: () => void;
  onOpenTemplatesModal?: () => void;
  onLogout: () => void;
  loading: boolean;
}

export const Sidebar: React.FC<SidebarProps> = ({
  health,
  auth,
  whatsAppStatus,
  activeTab,
  setActiveTab,
  stagedMode,
  setStagedMode,
  onRefresh,
  onOpenInviteModal,
  onOpenGuideModal,
  onOpenWhatsAppModal,
  onOpenTemplatesModal,
  onLogout,
  loading,
}) => {
  const [isMobileOpen, setIsMobileOpen] = useState(false);

  const closeMobile = () => setIsMobileOpen(false);

  return (
    <>
      {/* Mobile Top Navbar (shown on small screens) */}
      <div className="md:hidden flex items-center justify-between bg-[#111827] border-b border-[#25354b] px-4 py-3 sticky top-0 z-40">
        <div className="flex items-center space-x-2.5">
          <div className="h-8 w-8 rounded-lg bg-[#fd7e14] flex items-center justify-center shadow-md shadow-orange-500/20">
            <Shield className="h-4 w-4 text-white fill-white/20" />
          </div>
          <span className="font-bold text-base text-white tracking-tight">authentik</span>
          <span className="text-xs font-semibold px-1.5 py-0.2 rounded bg-[#1e2c3f] text-slate-300 border border-[#2c3f58]">
            Manager
          </span>
        </div>
        <button
          onClick={() => setIsMobileOpen(!isMobileOpen)}
          className="p-1.5 rounded-lg bg-[#16202e] text-slate-300 hover:text-white border border-[#25354b]"
          aria-label="Toggle navigation"
        >
          {isMobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {/* Backdrop for mobile drawer */}
      {isMobileOpen && (
        <div
          onClick={closeMobile}
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 md:hidden"
        />
      )}

      {/* Vertical Sidebar */}
      <aside
        className={`fixed md:sticky top-0 left-0 bottom-0 z-50 md:z-30 w-64 bg-[#111827] border-r border-[#25354b] flex flex-col justify-between transition-transform duration-200 ease-in-out md:translate-x-0 ${
          isMobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        } h-screen`}
      >
        <div className="flex-1 flex flex-col min-h-0 overflow-y-auto">
          
          {/* Top Brand & Instance Status */}
          <div className="p-4 border-b border-[#25354b] bg-[#0d131f]">
            <div className="flex items-center space-x-3">
              <div className="h-9 w-9 rounded-lg bg-[#fd7e14] flex items-center justify-center shadow-md shadow-orange-500/20 shrink-0">
                <Shield className="h-5 w-5 text-white fill-white/20 stroke-[2.2]" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center space-x-1.5">
                  <span className="font-bold text-lg text-white tracking-tight">authentik</span>
                  <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-[#1e2c3f] text-orange-300 border border-[#2c3f58]">
                    RBAC
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 font-medium truncate">
                  Access Manager
                </div>
              </div>
            </div>

            {/* Connection Status Badge */}
            <div className="mt-3 flex items-center justify-between p-2 rounded-lg bg-[#0b0f17] border border-[#25354b] text-[11px]">
              <div className="flex items-center space-x-2 truncate">
                <span className={`h-2 w-2 rounded-full shrink-0 ${health?.authentik_connected ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]' : 'bg-rose-500'}`} />
                <span className={`font-medium truncate ${health?.authentik_connected ? 'text-slate-300' : 'text-rose-400'}`} title={health?.authentik_url}>
                  {health?.authentik_connected ? (health.authentik_url.replace(/https?:\/\//, '') || 'Connected') : 'Offline'}
                </span>
              </div>
              {health?.demo_mode && (
                <span className="text-[9px] px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">
                  Demo
                </span>
              )}
            </div>

            {/* Quick Invite Button */}
            <button
              onClick={() => {
                onOpenInviteModal();
                closeMobile();
              }}
              className="mt-3 w-full flex items-center justify-center space-x-2 bg-[#fd7e14] hover:bg-[#ea6c0a] text-white text-xs font-semibold py-2 px-3 rounded-lg shadow transition-colors"
            >
              <UserPlus className="h-4 w-4" />
              <span>Create Invitation</span>
            </button>
          </div>

          {/* Navigation Items */}
          <div className="p-3 space-y-6">
            
            {/* Main Navigation Section */}
            <div>
              <div className="px-3 mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                Workspace
              </div>
              <nav className="space-y-1">
                {/* 1. Permission Matrix */}
                <button
                  onClick={() => {
                    setActiveTab('matrix');
                    closeMobile();
                  }}
                  className={`w-full flex items-center space-x-3 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                    activeTab === 'matrix'
                      ? 'bg-[#1e2c3f] text-white border border-[#2c3f58] shadow-sm font-semibold'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-[#16202e]'
                  }`}
                >
                  <Layers className={`h-4 w-4 ${activeTab === 'matrix' ? 'text-[#fd7e14]' : 'text-slate-400'}`} />
                  <span className="flex-1 text-left">Permission Matrix</span>
                </button>

                {/* 2. Invitations */}
                <button
                  onClick={() => {
                    setActiveTab('invites');
                    closeMobile();
                  }}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                    activeTab === 'invites'
                      ? 'bg-[#1e2c3f] text-white border border-[#2c3f58] shadow-sm font-semibold'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-[#16202e]'
                  }`}
                >
                  <div className="flex items-center space-x-3">
                    <UserPlus className={`h-4 w-4 ${activeTab === 'invites' ? 'text-[#fd7e14]' : 'text-slate-400'}`} />
                    <span>Invitations</span>
                  </div>
                  {health && health.active_invites_count > 0 && (
                    <span className="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-orange-500/20 text-[#fd7e14] border border-orange-500/30">
                      {health.active_invites_count}
                    </span>
                  )}
                </button>

                {/* 3. Audit Log */}
                <button
                  onClick={() => {
                    setActiveTab('audit');
                    closeMobile();
                  }}
                  className={`w-full flex items-center space-x-3 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                    activeTab === 'audit'
                      ? 'bg-[#1e2c3f] text-white border border-[#2c3f58] shadow-sm font-semibold'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-[#16202e]'
                  }`}
                >
                  <FileText className={`h-4 w-4 ${activeTab === 'audit' ? 'text-[#fd7e14]' : 'text-slate-400'}`} />
                  <span className="flex-1 text-left">Audit Trail</span>
                </button>

                {/* 4. Administration & Settings */}
                <button
                  onClick={() => {
                    setActiveTab('settings');
                    closeMobile();
                  }}
                  className={`w-full flex items-center space-x-3 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                    activeTab === 'settings'
                      ? 'bg-[#1e2c3f] text-white border border-[#2c3f58] shadow-sm font-semibold'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-[#16202e]'
                  }`}
                >
                  <Settings className={`h-4 w-4 ${activeTab === 'settings' ? 'text-[#fd7e14]' : 'text-slate-400'}`} />
                  <span className="flex-1 text-left">Admin & Settings</span>
                </button>
              </nav>
            </div>

            {/* Tools & Integrations Section */}
            <div>
              <div className="px-3 mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                Tools & Integrations
              </div>
              <div className="space-y-1">
                {/* Role Presets */}
                {onOpenTemplatesModal && (
                  <button
                    onClick={() => {
                      onOpenTemplatesModal();
                      closeMobile();
                    }}
                    className="w-full flex items-center space-x-3 px-3 py-2 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-[#16202e] transition-colors"
                  >
                    <Sparkles className="h-4 w-4 text-[#fd7e14]" />
                    <span className="flex-1 text-left">Role Presets</span>
                  </button>
                )}

                {/* WhatsApp Integration */}
                <button
                  onClick={() => {
                    onOpenWhatsAppModal();
                    closeMobile();
                  }}
                  className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-[#16202e] transition-colors"
                >
                  <div className="flex items-center space-x-3">
                    <MessageSquare className="h-4 w-4 text-emerald-400" />
                    <span>WhatsApp</span>
                  </div>
                  <span
                    className={`h-2 w-2 rounded-full ${
                      whatsAppStatus?.status === 'connected'
                        ? 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]'
                        : whatsAppStatus?.status === 'qr_ready'
                        ? 'bg-amber-400 animate-pulse'
                        : 'bg-slate-600'
                    }`}
                    title={whatsAppStatus?.status || 'Offline'}
                  />
                </button>

                {/* Setup Guide */}
                <button
                  onClick={() => {
                    onOpenGuideModal();
                    closeMobile();
                  }}
                  className="w-full flex items-center space-x-3 px-3 py-2 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-[#16202e] transition-colors"
                >
                  <BookOpen className="h-4 w-4 text-sky-400" />
                  <span className="flex-1 text-left">Setup Guide</span>
                </button>
              </div>
            </div>

            {/* Mode Switcher */}
            <div>
              <div className="px-3 mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                Mode
              </div>
              <div className="flex items-center bg-[#0b0f17] border border-[#25354b] rounded-lg p-0.5 text-xs">
                <button
                  onClick={() => setStagedMode(false)}
                  className={`flex-1 py-1.5 rounded-md text-[11px] font-medium text-center transition-all ${
                    !stagedMode
                      ? 'bg-[#1e2c3f] text-slate-100 border border-[#2c3f58] shadow-sm font-semibold'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                  title="Immediate mode: changes apply to Authentik API directly on click"
                >
                  Instant
                </button>
                <button
                  onClick={() => setStagedMode(true)}
                  className={`flex-1 py-1.5 rounded-md text-[11px] font-medium text-center transition-all ${
                    stagedMode
                      ? 'bg-[#fd7e14] text-white font-semibold shadow-sm'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                  title="Staged mode: queue multiple changes to review and apply together"
                >
                  Staged
                </button>
              </div>
            </div>

          </div>
        </div>

        {/* Footer: Refresh, Instance Link & User Profile */}
        <div className="p-3 border-t border-[#25354b] bg-[#0d131f] space-y-2">
          
          <div className="flex items-center justify-between text-xs text-slate-400 px-1">
            <div className="flex items-center space-x-1.5">
              <span>Sync status</span>
            </div>
            <button
              onClick={onRefresh}
              disabled={loading}
              className={`p-1.5 text-slate-400 hover:text-slate-200 hover:bg-[#1e2c3f] rounded-lg transition-all ${
                loading ? 'animate-spin text-[#fd7e14]' : ''
              }`}
              title="Refresh Matrix & Stats"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* User & Auth Pill */}
          <div className="flex items-center justify-between p-2 rounded-lg bg-[#0b0f17] border border-[#25354b]">
            {auth?.authenticated ? (
              <>
                <div className="flex items-center space-x-2.5 truncate">
                  <div className="h-7 w-7 rounded-full bg-[#1e2c3f] text-[#fd7e14] border border-[#2c3f58] flex items-center justify-center font-bold text-xs uppercase shrink-0">
                    {auth.user ? auth.user[0] : 'A'}
                  </div>
                  <div className="truncate">
                    <div className="text-xs font-semibold text-slate-200 truncate">
                      {auth.user || 'Administrator'}
                    </div>
                    <div className="text-[10px] text-slate-500 truncate">
                      {auth.auth_method === 'password' ? 'Password Auth' : 'Admin'}
                    </div>
                  </div>
                </div>
                {auth.auth_method !== 'none' && (
                  <button
                    onClick={onLogout}
                    className="p-1.5 text-slate-400 hover:text-rose-400 hover:bg-[#1e2c3f] rounded transition-colors"
                    title="Log Out"
                  >
                    <LogOut className="h-3.5 w-3.5" />
                  </button>
                )}
              </>
            ) : (
              <a
                href="/api/auth/oidc/login"
                className="w-full flex items-center justify-center space-x-1.5 text-xs text-slate-300 hover:text-white py-1 transition-colors"
              >
                <LogIn className="h-3.5 w-3.5 text-[#fd7e14]" />
                <span>OIDC Login</span>
              </a>
            )}
          </div>

        </div>
      </aside>
    </>
  );
};
