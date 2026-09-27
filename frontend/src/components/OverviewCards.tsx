import React from 'react';
import { Users, Server, ShieldAlert, ShieldCheck, Mail, Sliders } from 'lucide-react';
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
    <div className="bg-slate-900/70 border border-slate-800 rounded-xl px-4 py-2.5 mb-5 flex flex-wrap items-center justify-between gap-3 text-xs shadow-sm">
      {/* Metrics Summary Strip */}
      <div className="flex flex-wrap items-center gap-5 sm:gap-7 text-slate-300">
        <div className="flex items-center gap-2">
          <Server className="h-4 w-4 text-indigo-400" />
          <span>
            <strong className="text-white font-semibold">{health.total_apps}</strong> Services
          </span>
        </div>

        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-emerald-400" />
          <span>
            <strong className="text-white font-semibold">{health.total_users}</strong> Users
          </span>
        </div>

        <button
          onClick={onOpenInviteList}
          className="flex items-center gap-2 text-slate-300 hover:text-white transition-colors"
        >
          <Mail className="h-4 w-4 text-amber-400" />
          <span>
            <strong className="text-white font-semibold">{health.active_invites_count}</strong> Pending Invites
          </span>
        </button>

        <div className="flex items-center gap-1.5 text-[11px]">
          {health.unprotected_apps_count > 0 ? (
            <button
              onClick={onOpenProvisionModal}
              className="flex items-center gap-1.5 text-rose-300 bg-rose-500/15 border border-rose-500/30 px-2 py-0.5 rounded-full font-medium hover:bg-rose-500/25 transition-colors"
            >
              <ShieldAlert className="h-3 w-3 text-rose-400" />
              <span>{health.unprotected_apps_count} Unsecured Services</span>
            </button>
          ) : (
            <span className="flex items-center gap-1.5 text-emerald-300 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full font-medium">
              <ShieldCheck className="h-3 w-3 text-emerald-400" />
              <span>Default-Deny Enforced</span>
            </span>
          )}
        </div>
      </div>

      {/* Quick Action Link */}
      <button
        onClick={onOpenProvisionModal}
        className="flex items-center gap-1.5 text-[11px] text-indigo-400 hover:text-indigo-300 font-medium transition-colors ml-auto sm:ml-0"
      >
        <Sliders className="h-3 w-3" />
        <span>Manage Service Groups</span>
      </button>
    </div>
  );
};
