import React, { useState } from 'react';
import { X, Sliders, ShieldCheck, ShieldAlert, Check, Lock, Plus, Users } from 'lucide-react';
import { Application } from '../types';

interface ProvisionModalProps {
  isOpen: boolean;
  onClose: () => void;
  apps: Application[];
  onProvisionApp: (appPk: string, options?: any) => Promise<any>;
  onProvisionAll: (options?: any) => Promise<any>;
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
  const [createAdminGroups, setCreateAdminGroups] = useState<boolean>(true);

  if (!isOpen) return null;

  // Granular status classification
  const appsNeedingGranular = apps.filter(
    (a) => !a.has_granular_user_group || (createAdminGroups && !a.has_granular_admin_group)
  );
  const fullyGranularApps = apps.filter(
    (a) => a.has_granular_user_group && (!createAdminGroups || a.has_granular_admin_group)
  );
  const completelyUnprotected = apps.filter((a) => !a.is_protected);

  const handleProvisionOne = async (appPk: string) => {
    try {
      const res = await onProvisionApp(appPk, {
        create_user_group: true,
        create_admin_group: createAdminGroups,
      });
      setSuccessMessage(`Secured ${res.app_name} with dedicated granular groups!`);
      setTimeout(() => setSuccessMessage(null), 3500);
    } catch (err: any) {
      alert(`Error provisioning app: ${err.message}`);
    }
  };

  const handleProvisionAll = async () => {
    try {
      const res = await onProvisionAll({
        create_user_groups: true,
        create_admin_groups: createAdminGroups,
        include_already_secured: true,
      });
      setSuccessMessage(`Successfully provisioned granular groups across ${res.provisioned_count} application(s)!`);
      setTimeout(() => setSuccessMessage(null), 4000);
    } catch (err: any) {
      alert(`Error provisioning apps: ${err.message}`);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in">
      <div className="bg-[#111827] border border-[#25354b] rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        
        {/* Modal Header */}
        <div className="p-5 border-b border-[#25354b] bg-[#16202e] flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="h-9 w-9 rounded-lg bg-orange-500/15 border border-orange-500/30 text-[#fd7e14] flex items-center justify-center">
              <Sliders className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Application Access Provisioner</h3>
              <p className="text-xs text-slate-400">
                Create dedicated granular User & Admin groups and policy bindings for every service.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white hover:bg-[#1e2c3f] rounded-lg transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Modal Content */}
        <div className="p-5 overflow-y-auto flex-1 space-y-5">
          
          {successMessage && (
            <div className="p-3 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2">
              <Check className="h-4 w-4 shrink-0" />
              <span>{successMessage}</span>
            </div>
          )}

          {/* Explanation Box */}
          <div className="bg-[#0b0f17] border border-[#25354b] rounded-xl p-3.5 text-xs text-slate-300 space-y-2">
            <p className="font-semibold text-white flex items-center gap-1.5">
              <Lock className="h-3.5 w-3.5 text-[#fd7e14]" />
              <span>How Granular Groups Work in Authentik:</span>
            </p>
            <ul className="list-disc pl-4 space-y-1.5 text-slate-400 text-[11px]">
              <li>
                <strong>Additive Security:</strong> Keeps your existing bindings (such as <code className="text-[#fd7e14]">5AMT admin</code> or <code className="text-[#fd7e14]">5AMT Home</code>) completely intact.
              </li>
              <li>
                <strong>Individual Member Groups:</strong> Creates <code className="text-[#fd7e14]">App - &lt;AppName&gt;</code> so you can assign standard user access per service without granting wide household permissions.
              </li>
              <li>
                <strong>Individual Admin Groups:</strong> Creates <code className="text-[#fd7e14]">App - &lt;AppName&gt; Admin</code> for granular administration of specific apps.
              </li>
              <li>
                <strong>Policy Engine Mode:</strong> Configures Authentik to evaluate with <code className="text-[#fd7e14]">'any'</code> (OR logic) so members of either your admin group, home group, or dedicated app group gain access seamlessly.
              </li>
            </ul>
          </div>

          {/* Bulk Action Controls */}
          <div className="bg-[#16202e] border border-[#25354b] rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <label className="flex items-center space-x-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={createAdminGroups}
                  onChange={(e) => setCreateAdminGroups(e.target.checked)}
                  className="rounded border-[#25354b] bg-[#0b0f17] text-[#fd7e14] focus:ring-[#fd7e14] h-4 w-4"
                />
                <span className="text-xs font-semibold text-white">
                  Also create App Admin Groups (<code className="text-[#fd7e14]">App - &lt;Name&gt; Admin</code>)
                </span>
              </label>
              <p className="text-[11px] text-slate-400 mt-1 pl-6">
                Allows toggling both regular app member and app administrator roles in the Permission Matrix.
              </p>
            </div>

            {appsNeedingGranular.length > 0 && (
              <button
                onClick={handleProvisionAll}
                disabled={loading}
                className="shrink-0 bg-[#fd7e14] hover:bg-[#ea6c0a] disabled:opacity-50 text-white font-semibold text-xs px-4 py-2 rounded-lg transition-all shadow-sm flex items-center justify-center gap-1.5"
              >
                <Plus className="h-4 w-4" />
                <span>Provision All Missing ({appsNeedingGranular.length})</span>
              </button>
            )}
          </div>

          {/* Completely Unprotected Services Warning (if any) */}
          {completelyUnprotected.length > 0 && (
            <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-4 w-4 text-rose-400 shrink-0" />
                <span><strong>{completelyUnprotected.length}</strong> service(s) have ZERO policy bindings and are accessible to anyone!</span>
              </div>
            </div>
          )}

          {/* Apps Needing Granular RBAC Groups */}
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <h4 className="text-xs font-bold text-slate-300 flex items-center gap-1.5 uppercase tracking-wider">
                <Users className="h-4 w-4 text-[#fd7e14]" />
                <span>Services Awaiting Granular Groups ({appsNeedingGranular.length})</span>
              </h4>
            </div>

            {appsNeedingGranular.length === 0 ? (
              <div className="bg-[#0b0f17] border border-[#25354b] rounded-xl p-4 text-center text-xs text-emerald-400 flex items-center justify-center gap-2">
                <ShieldCheck className="h-4 w-4" />
                <span>All {apps.length} applications have dedicated granular User & Admin groups configured!</span>
              </div>
            ) : (
              <div className="space-y-2.5 max-h-72 overflow-y-auto pr-1">
                {appsNeedingGranular.map((app) => (
                  <div
                    key={app.pk}
                    className="bg-[#0b0f17] border border-[#25354b] hover:border-[#2c3f58] rounded-xl p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition-colors"
                  >
                    <div className="flex items-start space-x-3">
                      {app.meta_icon ? (
                        <img
                          src={app.meta_icon}
                          alt={app.name}
                          className="h-8 w-8 rounded-lg object-contain bg-[#111827] p-1 border border-[#25354b] shrink-0"
                        />
                      ) : (
                        <div className="h-8 w-8 rounded-lg bg-[#1e2c3f] text-[#fd7e14] flex items-center justify-center font-bold text-xs shrink-0 border border-[#2c3f58]">
                          {app.name.substring(0, 2).toUpperCase()}
                        </div>
                      )}
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="text-xs font-semibold text-slate-100">{app.name}</p>
                          {app.group && (
                            <span className="text-[10px] text-slate-400 bg-[#16202e] px-1.5 py-0.5 rounded border border-[#25354b]">
                              {app.group}
                            </span>
                          )}
                        </div>

                        {/* Existing bound groups pills */}
                        <div className="flex flex-wrap items-center gap-1 mt-1">
                          <span className="text-[10px] text-slate-500">Bound:</span>
                          {app.all_bound_groups && app.all_bound_groups.length > 0 ? (
                            app.all_bound_groups.map((bg) => (
                              <span
                                key={bg.pk}
                                className={`text-[10px] px-1.5 py-0.2 rounded font-mono ${
                                  bg.is_granular_user
                                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                    : bg.is_granular_admin
                                    ? 'bg-orange-500/10 text-[#fd7e14] border border-orange-500/20'
                                    : 'bg-[#16202e] text-slate-400 border border-[#25354b]'
                                }`}
                              >
                                {bg.name}
                              </span>
                            ))
                          ) : (
                            <span className="text-[10px] text-rose-400 italic">None (Wide Open)</span>
                          )}
                        </div>
                      </div>
                    </div>

                    <button
                      onClick={() => handleProvisionOne(app.pk)}
                      disabled={loading}
                      className="self-end sm:self-center flex items-center space-x-1.5 bg-[#16202e] hover:bg-[#fd7e14] text-slate-200 hover:text-white text-xs px-3 py-1.5 rounded-lg border border-[#25354b] hover:border-[#fd7e14] transition-all shrink-0"
                    >
                      <Plus className="h-3.5 w-3.5" />
                      <span>Provision Groups</span>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Fully Configured Granular Applications */}
          {fullyGranularApps.length > 0 && (
            <div>
              <h4 className="text-xs font-bold text-slate-400 mb-2 flex items-center gap-1.5 uppercase tracking-wider">
                <ShieldCheck className="h-4 w-4 text-emerald-400" />
                <span>Fully Configured Granular Services ({fullyGranularApps.length})</span>
              </h4>
              <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
                {fullyGranularApps.map((app) => (
                  <div
                    key={app.pk}
                    className="bg-[#0b0f17]/60 border border-[#25354b]/80 rounded-xl px-3 py-2 flex items-center justify-between text-xs"
                  >
                    <span className="text-slate-300 font-medium">{app.name}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-md font-mono">
                        {app.granular_user_group_name || 'App User'}
                      </span>
                      {app.granular_admin_group_name && (
                        <span className="text-[10px] text-[#fd7e14] bg-orange-500/10 border border-orange-500/20 px-2 py-0.5 rounded-md font-mono">
                          {app.granular_admin_group_name}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-[#25354b] bg-[#16202e] flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-xs font-medium text-slate-300 hover:bg-[#1e2c3f] transition-colors"
          >
            Close
          </button>
        </div>

      </div>
    </div>
  );
};
