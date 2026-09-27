import React from 'react';
import { Users, Server, ShieldAlert, ShieldCheck, Mail } from 'lucide-react';
import { HealthStatus } from '../types';

interface OverviewCardsProps {
  health: HealthStatus | null;
  onOpenProvisionModal: () => void;
  onOpenInviteList: () => void;
}

export const OverviewCards: React.FC<OverviewCardsProps> = ({
  health,
  onOpenProvisionModal,
  onOpenInviteList,
}) => {
  if (!health) return null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      
      {/* Total Users */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 shadow-sm flex items-center justify-between">
        <div>
          <p className="text-xs font-medium text-slate-400">Total Users</p>
          <p className="text-2xl font-bold text-white mt-1">{health.total_users}</p>
          <span className="text-[11px] text-emerald-400 flex items-center gap-1 mt-0.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400"></span> Authentik Core
          </span>
        </div>
        <div className="h-12 w-12 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
          <Users className="h-6 w-6" />
        </div>
      </div>

      {/* Total Applications */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 shadow-sm flex items-center justify-between">
        <div>
          <p className="text-xs font-medium text-slate-400">Configured Services</p>
          <p className="text-2xl font-bold text-white mt-1">{health.total_apps}</p>
          <p className="text-[11px] text-slate-400 mt-0.5">
            {health.total_apps - health.unprotected_apps_count} secured with RBAC
          </p>
        </div>
        <div className="h-12 w-12 rounded-xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center text-violet-400">
          <Server className="h-6 w-6" />
        </div>
      </div>

      {/* Security Health / Unprotected Apps */}
      <div
        onClick={health.unprotected_apps_count > 0 ? onOpenProvisionModal : undefined}
        className={`border rounded-xl p-4 shadow-sm flex items-center justify-between transition-all ${
          health.unprotected_apps_count > 0
            ? 'bg-rose-950/20 border-rose-500/40 cursor-pointer hover:bg-rose-950/30'
            : 'bg-emerald-950/20 border-emerald-500/30'
        }`}
      >
        <div>
          <p className="text-xs font-medium text-slate-400">Security Health</p>
          <p className={`text-2xl font-bold mt-1 ${health.unprotected_apps_count > 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
            {health.unprotected_apps_count > 0
              ? `${health.unprotected_apps_count} Unsecured`
              : 'All Secured'}
          </p>
          <p className="text-[11px] text-slate-400 mt-0.5">
            {health.unprotected_apps_count > 0
              ? 'Click to auto-lock with RBAC'
              : 'Default-deny enforced'}
          </p>
        </div>
        <div
          className={`h-12 w-12 rounded-xl border flex items-center justify-center ${
            health.unprotected_apps_count > 0
              ? 'bg-rose-500/20 border-rose-500/30 text-rose-400 animate-pulse'
              : 'bg-emerald-500/20 border-emerald-500/30 text-emerald-400'
          }`}
        >
          {health.unprotected_apps_count > 0 ? (
            <ShieldAlert className="h-6 w-6" />
          ) : (
            <ShieldCheck className="h-6 w-6" />
          )}
        </div>
      </div>

      {/* Pending Invitations */}
      <div
        onClick={onOpenInviteList}
        className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 shadow-sm flex items-center justify-between cursor-pointer hover:bg-slate-800/50 transition-colors"
      >
        <div>
          <p className="text-xs font-medium text-slate-400">Pending Invites</p>
          <p className="text-2xl font-bold text-white mt-1">{health.active_invites_count}</p>
          <p className="text-[11px] text-slate-400 mt-0.5">Awaiting user registration</p>
        </div>
        <div className="h-12 w-12 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
          <Mail className="h-6 w-6" />
        </div>
      </div>

    </div>
  );
};
