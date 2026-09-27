import React from 'react';
import { 
  ShieldCheck, 
  RefreshCw, 
  UserPlus, 
  Layers, 
  FileText, 
  BookOpen, 
  CheckSquare, 
  Zap, 
  LogOut, 
  LogIn,
  Sliders,
  MessageSquare
} from 'lucide-react';
import { HealthStatus, AuthStatus, WhatsAppStatus } from '../types';

interface HeaderProps {
  health: HealthStatus | null;
  auth: AuthStatus | null;
  whatsAppStatus: WhatsAppStatus | null;
  activeTab: 'matrix' | 'invites' | 'audit';
  setActiveTab: (tab: 'matrix' | 'invites' | 'audit') => void;
  stagedMode: boolean;
  setStagedMode: (val: boolean) => void;
  onRefresh: () => void;
  onOpenInviteModal: () => void;
  onOpenGuideModal: () => void;
  onOpenProvisionModal: () => void;
  onOpenWhatsAppModal: () => void;
  onLogout: () => void;
  loading: boolean;
}

export const Header: React.FC<HeaderProps> = ({
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
  onOpenProvisionModal,
  onOpenWhatsAppModal,
  onLogout,
  loading,
}) => {
  return (
    <header className="bg-slate-900 border-b border-slate-800 sticky top-0 z-30 shadow-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          
          {/* Left: Brand & Status */}
          <div className="flex items-center space-x-3">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <ShieldCheck className="h-6 w-6 text-white" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-lg text-white tracking-tight">Authentik</span>
                <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                  Access Manager
                </span>
                {health?.demo_mode && (
                  <span className="text-xs font-medium px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">
                    Demo Mode
                  </span>
                )}
              </div>
              <div className="flex items-center space-x-2 text-xs text-slate-400">
                <span className="flex items-center gap-1">
                  <span className={`h-2 w-2 rounded-full ${health?.authentik_connected ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`} />
                  {health?.authentik_connected ? 'Authentik Online' : 'Authentik Offline'}
                </span>
                <span>•</span>
                <span className="truncate max-w-[200px]" title={health?.authentik_url}>
                  {health?.authentik_url}
                </span>
              </div>
            </div>
          </div>

          {/* Center: Tabs */}
          <nav className="hidden md:flex space-x-1 bg-slate-950/60 p-1 rounded-xl border border-slate-800/80">
            <button
              onClick={() => setActiveTab('matrix')}
              className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === 'matrix'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <Layers className="h-4 w-4" />
              <span>Permission Matrix</span>
            </button>
            <button
              onClick={() => setActiveTab('invites')}
              className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === 'invites'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <UserPlus className="h-4 w-4" />
              <span>Invitations</span>
              {health && health.active_invites_count > 0 && (
                <span className="ml-1 px-1.5 py-0.2 rounded-full text-[10px] bg-indigo-400/20 text-indigo-200">
                  {health.active_invites_count}
                </span>
              )}
            </button>
            <button
              onClick={() => setActiveTab('audit')}
              className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === 'audit'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <FileText className="h-4 w-4" />
              <span>Audit Log</span>
            </button>
          </nav>

          {/* Right: Actions, Mode Toggle, User */}
          <div className="flex items-center space-x-3">
            
            {/* Staged vs Instant Mode Toggle */}
            <div className="hidden lg:flex items-center bg-slate-950/60 border border-slate-800 rounded-lg p-0.5 text-xs">
              <button
                onClick={() => setStagedMode(false)}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md transition-colors ${
                  !stagedMode
                    ? 'bg-amber-500/20 text-amber-300 font-medium border border-amber-500/30'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Changes apply to Authentik immediately when toggled"
              >
                <Zap className="h-3 w-3 text-amber-400" />
                <span>Instant</span>
              </button>
              <button
                onClick={() => setStagedMode(true)}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md transition-colors ${
                  stagedMode
                    ? 'bg-indigo-600 text-white font-medium shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Review and confirm all permission changes before applying"
              >
                <CheckSquare className="h-3 w-3" />
                <span>Staged</span>
              </button>
            </div>

            {/* Quick Actions */}
            <button
              onClick={onOpenWhatsAppModal}
              className={`flex items-center space-x-1.5 text-xs font-medium px-2.5 py-1.5 rounded-lg border transition-colors ${
                whatsAppStatus?.status === 'connected'
                  ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/20'
                  : whatsAppStatus?.status === 'qr_ready'
                  ? 'bg-amber-500/10 text-amber-300 border-amber-500/30 hover:bg-amber-500/20 animate-pulse'
                  : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'
              }`}
              title={
                whatsAppStatus?.status === 'connected'
                  ? `WhatsApp Linked (+${whatsAppStatus.phone})`
                  : 'Configure WhatsApp Bridge'
              }
            >
              <MessageSquare className="h-3.5 w-3.5 text-emerald-400" />
              <span className="hidden sm:inline">
                {whatsAppStatus?.status === 'connected' ? 'WhatsApp' : 'Link WhatsApp'}
              </span>
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  whatsAppStatus?.status === 'connected'
                    ? 'bg-emerald-400'
                    : whatsAppStatus?.status === 'qr_ready'
                    ? 'bg-amber-400'
                    : 'bg-slate-500'
                }`}
              />
            </button>

            <button
              onClick={onOpenInviteModal}
              className="flex items-center space-x-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold px-3 py-1.5 rounded-lg shadow-sm transition-colors"
            >
              <UserPlus className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Invite User</span>
            </button>

            <button
              onClick={onOpenProvisionModal}
              className="flex items-center space-x-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium px-3 py-1.5 rounded-lg border border-slate-700 transition-colors"
              title="Auto-provision App Groups & Policy Bindings"
            >
              <Sliders className="h-3.5 w-3.5 text-indigo-400" />
              <span className="hidden sm:inline">Provision Apps</span>
            </button>

            <button
              onClick={onOpenGuideModal}
              className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition-colors"
              title="Authentik Setup Guide & Expression Policy"
            >
              <BookOpen className="h-4 w-4" />
            </button>

            <button
              onClick={onRefresh}
              disabled={loading}
              className={`p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition-colors ${loading ? 'animate-spin text-indigo-400' : ''}`}
              title="Refresh Matrix"
            >
              <RefreshCw className="h-4 w-4" />
            </button>

            {/* User / Auth Info */}
            <div className="flex items-center pl-2 border-l border-slate-800">
              {auth?.authenticated ? (
                <div className="flex items-center space-x-2">
                  <div className="h-7 w-7 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 flex items-center justify-center font-bold text-xs uppercase">
                    {auth.user ? auth.user[0] : 'A'}
                  </div>
                  <span className="hidden xl:inline text-xs font-medium text-slate-300">
                    {auth.user || 'Admin'}
                  </span>
                  {auth.auth_method !== 'none' && (
                    <button
                      onClick={onLogout}
                      className="p-1 text-slate-400 hover:text-rose-400 hover:bg-slate-800 rounded transition-colors"
                      title="Log Out"
                    >
                      <LogOut className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              ) : (
                <a
                  href="/api/auth/oidc/login"
                  className="flex items-center space-x-1.5 bg-slate-800 hover:bg-slate-700 text-indigo-400 text-xs px-2.5 py-1.5 rounded-lg border border-slate-700"
                >
                  <LogIn className="h-3.5 w-3.5" />
                  <span>OIDC Login</span>
                </a>
              )}
            </div>

          </div>

        </div>
      </div>
    </header>
  );
};
