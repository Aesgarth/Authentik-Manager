import React from 'react';
import { AlertTriangle, Lock, ArrowRight } from 'lucide-react';
import { Application } from '../types';

interface SecurityBannerProps {
  unprotectedApps: Application[];
  onLockdown: () => void;
  loading: boolean;
}

export const SecurityBanner: React.FC<SecurityBannerProps> = ({
  unprotectedApps,
  onLockdown,
  loading,
}) => {
  if (unprotectedApps.length === 0) return null;

  return (
    <div className="mb-6 rounded-xl bg-gradient-to-r from-rose-950/60 via-slate-900 to-slate-900 border border-rose-500/40 p-4 shadow-lg">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        
        <div className="flex items-start space-x-3">
          <div className="p-2 rounded-lg bg-rose-500/20 text-rose-400 border border-rose-500/30 flex-shrink-0 mt-0.5">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div>
            <h4 className="text-sm font-semibold text-rose-300 flex items-center gap-2">
              Security Notice: {unprotectedApps.length} Unrestricted Application{unprotectedApps.length > 1 ? 's' : ''} Detected
            </h4>
            <p className="text-xs text-slate-300 mt-1 max-w-3xl leading-relaxed">
              In Authentik, applications without explicit Policy Bindings are accessible to <strong>any authenticated user</strong> by default.
              The following services are currently open:
              <span className="font-semibold text-white ml-1">
                {unprotectedApps.map((a) => a.name).join(', ')}
              </span>.
            </p>
          </div>
        </div>

        <button
          onClick={onLockdown}
          disabled={loading}
          className="flex items-center space-x-2 bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white font-medium text-xs px-4 py-2.5 rounded-lg shadow transition-colors flex-shrink-0 self-end sm:self-center"
        >
          <Lock className="h-4 w-4" />
          <span>{loading ? 'Locking Down...' : 'Auto-Provision & Secure All'}</span>
          <ArrowRight className="h-3.5 w-3.5" />
        </button>

      </div>
    </div>
  );
};
