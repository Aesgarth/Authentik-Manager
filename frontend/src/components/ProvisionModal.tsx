import React, { useState } from 'react';
import { X, Sliders, ShieldCheck, ShieldAlert, Check, Lock } from 'lucide-react';
import { Application } from '../types';

interface ProvisionModalProps {
  isOpen: boolean;
  onClose: () => void;
  apps: Application[];
  onProvisionApp: (appPk: string, customGroupName?: string) => Promise<any>;
  onProvisionAll: () => Promise<any>;
  loading: boolean;
}

export const ProvisionModal: React.FC<ProvisionModalProps> = ({
  isOpen,
  onClose,
  apps,
  onProvisionApp,
  onProvisionAll,
  loading,
}) => {
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const unprotected = apps.filter((a) => !a.is_protected);
  const protectedApps = apps.filter((a) => a.is_protected);

  const handleProvisionOne = async (appPk: string) => {
    try {
      const res = await onProvisionApp(appPk);
      setSuccessMessage(`Secured ${res.app_name} with group '${res.group_name}'!`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err: any) {
      alert(`Error provisioning app: ${err.message}`);
    }
  };

  const handleProvisionAll = async () => {
    try {
      const res = await onProvisionAll();
      setSuccessMessage(`Successfully secured ${res.provisioned_count} applications!`);
      setTimeout(() => setSuccessMessage(null), 3500);
    } catch (err: any) {
      alert(`Error provisioning apps: ${err.message}`);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        
        {/* Modal Header */}
        <div className="p-5 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="h-9 w-9 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center">
              <Sliders className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Application Access Provisioner</h3>
              <p className="text-xs text-slate-400">
                Enforce Role-Based Access Control (RBAC) across your homelab services.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Modal Content */}
        <div className="p-5 overflow-y-auto flex-1 space-y-4">
          
          {successMessage && (
            <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs flex items-center gap-2">
              <Check className="h-4 w-4" />
              <span>{successMessage}</span>
            </div>
          )}

          {/* Explanation Box */}
          <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5 text-xs text-slate-300 space-y-2">
            <p className="font-semibold text-slate-200 flex items-center gap-1.5">
              <Lock className="h-3.5 w-3.5 text-indigo-400" />
              <span>How Auto-Provisioning Secures Your Network:</span>
            </p>
            <ul className="list-disc pl-4 space-y-1 text-slate-400 text-[11px]">
              <li>Creates a dedicated group (e.g. <code className="text-indigo-300">App - Jellyfin</code>) in Authentik.</li>
              <li>Attaches a strict <strong>Policy Binding</strong> to the service (<code className="text-indigo-300">target = app, group = group</code>).</li>
              <li>Ensures default-deny: Authentik will immediately reject any user not explicitly granted membership in that group.</li>
              <li>Adds your admin account automatically to guarantee you are never locked out.</li>
            </ul>
          </div>

          {/* Unprotected Services Section */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-xs font-semibold text-rose-300 flex items-center gap-1.5">
                <ShieldAlert className="h-4 w-4 text-rose-400" />
                <span>Unrestricted Applications ({unprotected.length})</span>
              </h4>
              {unprotected.length > 0 && (
                <button
                  onClick={handleProvisionAll}
                  disabled={loading}
                  className="text-xs bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white font-medium px-3 py-1 rounded-lg transition-colors"
                >
                  Secure All ({unprotected.length})
                </button>
              )}
            </div>

            {unprotected.length === 0 ? (
              <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 text-center text-xs text-emerald-400 flex items-center justify-center gap-2">
                <ShieldCheck className="h-4 w-4" />
                <span>All applications currently have active policy bindings!</span>
              </div>
            ) : (
              <div className="space-y-2">
                {unprotected.map((app) => (
                  <div
                    key={app.pk}
                    className="bg-slate-950 border border-rose-500/20 rounded-xl p-3 flex items-center justify-between"
                  >
                    <div className="flex items-center space-x-3">
                      {app.meta_icon ? (
                        <img
                          src={app.meta_icon}
                          alt={app.name}
                          className="h-7 w-7 rounded object-contain bg-slate-900 p-0.5"
                        />
                      ) : (
                        <div className="h-7 w-7 rounded bg-indigo-500/10 text-indigo-400 flex items-center justify-center font-bold text-xs">
                          {app.name.substring(0, 2).toUpperCase()}
                        </div>
                      )}
                      <div>
                        <p className="text-xs font-semibold text-slate-200">{app.name}</p>
                        <p className="text-[11px] text-rose-400">Currently open to all users</p>
                      </div>
                    </div>

                    <button
                      onClick={() => handleProvisionOne(app.pk)}
                      disabled={loading}
                      className="flex items-center space-x-1.5 bg-slate-800 hover:bg-indigo-600 text-slate-200 hover:text-white text-xs px-3 py-1.5 rounded-lg border border-slate-700 hover:border-indigo-500 transition-colors"
                    >
                      <Lock className="h-3 w-3" />
                      <span>Create Group & Lock</span>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Already Secured Services */}
          {protectedApps.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-slate-400 mb-2 flex items-center gap-1.5">
                <ShieldCheck className="h-4 w-4 text-emerald-400" />
                <span>Secured Services ({protectedApps.length})</span>
              </h4>
              <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
                {protectedApps.map((app) => (
                  <div
                    key={app.pk}
                    className="bg-slate-950/60 border border-slate-800/80 rounded-xl px-3 py-2 flex items-center justify-between text-xs"
                  >
                    <span className="text-slate-300 font-medium">{app.name}</span>
                    <span className="text-[11px] text-emerald-400 font-mono">
                      {app.bound_group_name || 'Policy Bound'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-slate-800 bg-slate-900/50 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-medium text-slate-300 hover:bg-slate-800 transition-colors"
          >
            Close
          </button>
        </div>

      </div>
    </div>
  );
};
