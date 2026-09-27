import React, { useState } from 'react';
import { Mail, Copy, Check, Trash2, RefreshCw, Plus, Clock } from 'lucide-react';
import { TrackedInvite } from '../types';

interface InviteListProps {
  invites: TrackedInvite[];
  onOpenInviteModal: () => void;
  onRevokeInvite: (invitation_pk: string) => Promise<void>;
  onSyncRedemptions: () => Promise<void>;
  loading?: boolean;
}

export const InviteList: React.FC<InviteListProps> = ({
  invites,
  onOpenInviteModal,
  onRevokeInvite,
  onSyncRedemptions,
}) => {
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  const handleCopy = (inv: TrackedInvite) => {
    navigator.clipboard.writeText(inv.invite_url);
    setCopiedId(inv.invitation_pk);
    setTimeout(() => setCopiedId(null), 2500);
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      await onSyncRedemptions();
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="bg-[#111827] border border-[#25354b] rounded-2xl shadow-xl overflow-hidden flex flex-col">
      
      {/* Header */}
      <div className="p-4 border-b border-[#25354b] bg-[#16202e] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <Mail className="h-5 w-5 text-[#fd7e14]" />
            <span>Invitation Tracker</span>
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Active and redeemed invitation links with pre-assigned application permissions.
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={handleSync}
            disabled={syncing}
            className="flex items-center space-x-1.5 bg-[#0b0f17] hover:bg-[#1e2c3f] text-slate-200 text-xs px-3 py-1.5 rounded-lg border border-[#25354b] transition-colors"
            title="Scan Authentik for newly registered users and match against pending invites"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${syncing ? 'animate-spin text-[#fd7e14]' : ''}`} />
            <span>{syncing ? 'Checking...' : 'Check Redemptions'}</span>
          </button>

          <button
            onClick={onOpenInviteModal}
            className="flex items-center space-x-1.5 bg-[#fd7e14] hover:bg-[#ea6c0a] text-white text-xs font-semibold px-3 py-1.5 rounded-lg shadow-sm transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>Create Invite</span>
          </button>
        </div>
      </div>

      {/* Invites Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-[#0b0f17] border-b border-[#25354b] text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              <th className="px-4 py-3">Recipient / Note</th>
              <th className="px-4 py-3">Pre-Assigned Services</th>
              <th className="px-4 py-3">Expires At</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#25354b]/50">
            {invites.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-12 text-center text-slate-400 text-xs">
                  <div className="max-w-xs mx-auto space-y-2">
                    <p className="font-medium text-slate-300">No invitations created yet</p>
                    <p className="text-slate-500 text-[11px]">
                      Generate an invite link to onboard a new user with pre-assigned service access.
                    </p>
                    <button
                      onClick={onOpenInviteModal}
                      className="mt-2 inline-flex items-center space-x-1.5 bg-[#fd7e14] hover:bg-[#ea6c0a] text-white text-xs px-3 py-1.5 rounded-lg font-medium"
                    >
                      <Plus className="h-3.5 w-3.5" />
                      <span>Create First Invite</span>
                    </button>
                  </div>
                </td>
              </tr>
            ) : (
              invites.map((inv) => {
                const isPending = inv.status === 'pending';
                const isRedeemed = inv.status === 'redeemed';
                const isRevoked = inv.status === 'revoked';

                return (
                  <tr key={inv.id} className="hover:bg-[#16202e]/40 transition-colors">
                    
                    {/* Name, Email & Phone */}
                    <td className="px-4 py-3">
                      <div className="font-semibold text-xs text-slate-200">{inv.name}</div>
                      <div className="flex flex-col text-[11px] text-slate-400 mt-0.5 space-y-0.5">
                        {inv.email && <span>{inv.email}</span>}
                        {inv.phone && (
                          <span className="flex items-center gap-1 text-slate-300 font-mono">
                            <span className="text-emerald-400">📱</span> {inv.phone}
                            {inv.whatsapp_sent && (
                              <span className="text-[10px] text-emerald-400 bg-emerald-500/10 px-1.5 py-0.2 rounded border border-emerald-500/20">
                                WhatsApp Sent
                              </span>
                            )}
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Pre-assigned Apps */}
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1 max-w-sm">
                        {inv.assigned_apps.length > 0 ? (
                          inv.assigned_apps.map((app) => (
                            <span
                              key={app}
                              className="px-2 py-0.5 rounded text-[11px] bg-orange-500/10 text-[#fd7e14] border border-orange-500/20"
                            >
                              {app}
                            </span>
                          ))
                        ) : (
                          <span className="text-[11px] text-slate-500">None (General access)</span>
                        )}
                      </div>
                    </td>

                    {/* Expiration */}
                    <td className="px-4 py-3 text-xs text-slate-300">
                      {inv.expires_at ? (
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3 text-slate-500" />
                          {new Date(inv.expires_at).toLocaleDateString()}
                        </span>
                      ) : (
                        <span className="text-slate-500">Never</span>
                      )}
                    </td>

                    {/* Status Badge */}
                    <td className="px-4 py-3">
                      {isRedeemed ? (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                          Redeemed {inv.redeemed_by && `by ${inv.redeemed_by}`}
                        </span>
                      ) : isRevoked ? (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-[#1e2c3f] text-slate-400 border border-[#2c3f58]">
                          Revoked
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-orange-500/15 text-[#fd7e14] border border-orange-500/30 animate-pulse">
                          Pending Signup
                        </span>
                      )}
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end space-x-1.5">
                        {isPending && (
                          <>
                            {inv.phone && (
                              <a
                                href={`https://wa.me/${inv.phone.replace(/[^\d]/g, '')}?text=${encodeURIComponent(
                                  `👋 Hi ${inv.name}! Here is your personal access link to our home services (${inv.assigned_apps.join(', ')}): ${inv.invite_url}`
                                )}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                title="Share via WhatsApp"
                                className="p-1.5 rounded-lg bg-emerald-950/40 hover:bg-emerald-900/60 text-emerald-400 hover:text-emerald-300 border border-emerald-500/30 transition-colors"
                              >
                                <span className="text-xs">📱</span>
                              </a>
                            )}
                            <button
                              onClick={() => handleCopy(inv)}
                              title="Copy Invite Link"
                              className="p-1.5 rounded-lg bg-[#0b0f17] hover:bg-[#1e2c3f] text-slate-300 hover:text-white border border-[#25354b] transition-colors"
                            >
                              {copiedId === inv.invitation_pk ? (
                                <Check className="h-3.5 w-3.5 text-emerald-400" />
                              ) : (
                                <Copy className="h-3.5 w-3.5" />
                              )}
                            </button>
                            <button
                              onClick={() => onRevokeInvite(inv.invitation_pk)}
                              title="Revoke Invite"
                              className="p-1.5 rounded-lg bg-[#0b0f17] hover:bg-rose-950/60 text-slate-400 hover:text-rose-400 border border-[#25354b] transition-colors"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </>
                        )}
                      </div>
                    </td>

                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

    </div>
  );
};
