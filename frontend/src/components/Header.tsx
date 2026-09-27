import React from 'react';
import { 
  Shield, 
  RefreshCw, 
  UserPlus, 
  Layers, 
  FileText, 
  BookOpen, 
  LogOut, 
  LogIn,
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
  onOpenWhatsAppModal,
  onLogout,
  loading,
}) => {
  return (
    <header className="bg-[#111827] border-b border-[#25354b] sticky top-0 z-30 shadow-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          
          {/* Left: Authentik Brand & Instance Status */}
          <div className="flex items-center space-x-3.5">
            {/* Authentik Orange Hexagon/Shield Emblem */}
            <div className="h-9 w-9 rounded-lg bg-[#fd7e14] flex items-center justify-center shadow-md shadow-orange-500/20">
              <Shield className="h-5 w-5 text-white fill-white/20 stroke-[2.2]" />
            </div>
            
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-lg text-white tracking-tight font-sans">authentik</span>
                <span className="text-slate-500 font-light text-base">|</span>
                <span className="text-xs font-semibold px-2 py-0.5 rounded bg-[#1e2c3f] text-slate-300 border border-[#2c3f58]">
                  Access Manager
                </span>
                {health?.demo_mode && (
                  <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">
                    Demo Mode
                  </span>
                )}
              </div>
              
              <div className="flex items-center space-x-2 text-[11px] text-slate-400 mt-0.5">
                <span className="flex items-center gap-1.5 font-medium">
                  <span className={`h-2 w-2 rounded-full ${health?.authentik_connected ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]' : 'bg-rose-500'}`} />
                  <span className={health?.authentik_connected ? 'text-slate-300' : 'text-rose-400'}>
                    {health?.authentik_connected ? 'Connected' : 'Offline'}
                  </span>
                </span>
                <span className="text-slate-600">•</span>
                <span className="truncate max-w-[220px] font-mono text-slate-400" title={health?.authentik_url}>
                  {health?.authentik_url || 'https://auth.5amt.co.uk'}
                </span>
              </div>
            </div>
          </div>

          {/* Center: PatternFly Style Horizontal Underline Navigation */}
          <nav className="hidden md:flex items-center h-full space-x-6 border-b border-transparent">
            <button
              onClick={() => setActiveTab('matrix')}
              className={`h-16 flex items-center space-x-2 px-1 text-xs font-semibold tracking-wide transition-all border-b-2 ${
                activeTab === 'matrix'
                  ? 'border-[#fd7e14] text-white'
                  : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-600'
              }`}
            >
              <Layers className={`h-4 w-4 ${activeTab === 'matrix' ? 'text-[#fd7e14]' : 'text-slate-400'}`} />
              <span>Permission Matrix</span>
            </button>

            <button
              onClick={() => setActiveTab('invites')}
              className={`h-16 flex items-center space-x-2 px-1 text-xs font-semibold tracking-wide transition-all border-b-2 ${
                activeTab === 'invites'
                  ? 'border-[#fd7e14] text-white'
                  : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-600'
              }`}
            >
              <UserPlus className={`h-4 w-4 ${activeTab === 'invites' ? 'text-[#fd7e14]' : 'text-slate-400'}`} />
              <span>Invitations</span>
              {health && health.active_invites_count > 0 && (
                <span className="ml-1 px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-orange-500/20 text-[#fd7e14] border border-orange-500/30">
                  {health.active_invites_count}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab('audit')}
              className={`h-16 flex items-center space-x-2 px-1 text-xs font-semibold tracking-wide transition-all border-b-2 ${
                activeTab === 'audit'
                  ? 'border-[#fd7e14] text-white'
                  : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-600'
              }`}
            >
              <FileText className={`h-4 w-4 ${activeTab === 'audit' ? 'text-[#fd7e14]' : 'text-slate-400'}`} />
              <span>Audit Log</span>
            </button>
          </nav>

          {/* Right: Mode Toggle, WhatsApp, Actions, User */}
          <div className="flex items-center space-x-3">
            
            {/* Instant vs Staged Mode Switcher */}
            <div className="hidden lg:flex items-center bg-[#0b0f17] border border-[#25354b] rounded-lg p-0.5 text-xs">
              <button
                onClick={() => setStagedMode(false)}
                className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${
                  !stagedMode
                    ? 'bg-[#1e2c3f] text-slate-100 border border-[#2c3f58] shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Immediate mode: changes apply to Authentik API directly on click"
              >
                Instant
              </button>
              <button
                onClick={() => setStagedMode(true)}
                className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${
                  stagedMode
                    ? 'bg-[#fd7e14] text-white font-semibold shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Staged mode: queue multiple changes to review and apply together"
              >
                Staged
              </button>
            </div>

            {/* WhatsApp Integration Pill */}
            <button
              onClick={onOpenWhatsAppModal}
              className={`flex items-center space-x-1.5 text-xs px-2.5 py-1.5 rounded-lg border transition-all ${
                whatsAppStatus?.status === 'connected'
                  ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/20'
                  : whatsAppStatus?.status === 'qr_ready'
                  ? 'bg-amber-500/10 text-amber-300 border-amber-500/30 hover:bg-amber-500/20 animate-pulse'
                  : 'bg-[#16202e] text-slate-400 border-[#25354b] hover:bg-[#1e2c3f] hover:text-slate-200'
              }`}
              title={
                whatsAppStatus?.status === 'connected'
                  ? `WhatsApp Linked (+${whatsAppStatus.phone})`
                  : 'Pair WhatsApp for Invites'
              }
            >
              <MessageSquare className="h-3.5 w-3.5 text-emerald-400" />
              <span className="hidden sm:inline text-[11px] font-medium">
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

            {/* Refresh Button */}
            <button
              onClick={onRefresh}
              disabled={loading}
              className={`p-1.5 text-slate-400 hover:text-slate-200 hover:bg-[#1e2c3f] border border-transparent hover:border-[#2c3f58] rounded-lg transition-all ${
                loading ? 'animate-spin text-[#fd7e14]' : ''
              }`}
              title="Refresh Matrix"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>

            {/* Documentation / Guide */}
            <button
              onClick={onOpenGuideModal}
              className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-[#1e2c3f] border border-transparent hover:border-[#2c3f58] rounded-lg transition-all"
              title="Authentik Setup Guide & Expression Policy"
            >
              <BookOpen className="h-3.5 w-3.5" />
            </button>

            {/* Primary Action Button: Authentik Orange */}
            <button
              onClick={onOpenInviteModal}
              className="flex items-center space-x-1.5 bg-[#fd7e14] hover:bg-[#ea6c0a] text-white text-xs font-semibold px-3.5 py-1.5 rounded-lg shadow-sm transition-colors"
            >
              <UserPlus className="h-3.5 w-3.5" />
              <span>Invite</span>
            </button>

            {/* User Avatar / Auth */}
            <div className="flex items-center pl-2 border-l border-[#25354b]">
              {auth?.authenticated ? (
                <div className="flex items-center space-x-2">
                  <div className="h-7 w-7 rounded-full bg-[#1e2c3f] text-[#fd7e14] border border-[#2c3f58] flex items-center justify-center font-bold text-xs uppercase">
                    {auth.user ? auth.user[0] : 'A'}
                  </div>
                  <span className="hidden xl:inline text-xs font-medium text-slate-300">
                    {auth.user || 'Admin'}
                  </span>
                  {auth.auth_method !== 'none' && (
                    <button
                      onClick={onLogout}
                      className="p-1 text-slate-400 hover:text-rose-400 hover:bg-[#1e2c3f] rounded transition-colors"
                      title="Log Out"
                    >
                      <LogOut className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              ) : (
                <a
                  href="/api/auth/oidc/login"
                  className="flex items-center space-x-1.5 bg-[#16202e] hover:bg-[#1e2c3f] text-slate-200 text-xs px-2.5 py-1.5 rounded-lg border border-[#25354b]"
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
