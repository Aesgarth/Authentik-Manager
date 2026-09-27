import React, { useState } from 'react';
import { X, Copy, Check, UserPlus, Link, Mail, MessageSquare, ExternalLink } from 'lucide-react';
import { Application, TrackedInvite } from '../types';

interface InviteModalProps {
  isOpen: boolean;
  onClose: () => void;
  apps: Application[];
  appGroupMap: Record<string, string | null>;
  isWhatsAppConnected?: boolean;
  onCreateInvite: (params: {
    name: string;
    email?: string;
    phone?: string;
    send_via_whatsapp?: boolean;
    custom_message?: string;
    expires_in_days: number;
    single_use: boolean;
    group_pks: string[];
    app_names: string[];
  }) => Promise<TrackedInvite>;
}

export const InviteModal: React.FC<InviteModalProps> = ({
  isOpen,
  onClose,
  apps,
  appGroupMap,
  isWhatsAppConnected = false,
  onCreateInvite,
}) => {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [sendViaWhatsapp, setSendViaWhatsapp] = useState(false);
  const [expiresInDays, setExpiresInDays] = useState(7);
  const [singleUse, setSingleUse] = useState(true);
  const [selectedApps, setSelectedApps] = useState<Record<string, boolean>>({});
  const [createdInvite, setCreatedInvite] = useState<TrackedInvite | null>(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleToggleApp = (appPk: string) => {
    setSelectedApps((prev) => ({
      ...prev,
      [appPk]: !prev[appPk],
    }));
  };

  const handleSelectAll = () => {
    const all: Record<string, boolean> = {};
    apps.forEach((a) => {
      if (a.bound_group_pk) all[a.pk] = true;
    });
    setSelectedApps(all);
  };

  const handleClearAll = () => {
    setSelectedApps({});
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Please provide a name or note for this invitation.');
      return;
    }

    // Collect target groups and app names
    const targetGroupPks: string[] = [];
    const targetAppNames: string[] = [];

    apps.forEach((a) => {
      if (selectedApps[a.pk]) {
        const groupPk = a.bound_group_pk || appGroupMap[a.pk];
        if (groupPk) {
          targetGroupPks.push(groupPk);
          targetAppNames.push(a.name);
        }
      }
    });

    try {
      setLoading(true);
      setError(null);
      const res = await onCreateInvite({
        name: name.trim(),
        email: email.trim() || undefined,
        phone: phone.trim() || undefined,
        send_via_whatsapp: sendViaWhatsapp,
        expires_in_days: expiresInDays,
        single_use: singleUse,
        group_pks: targetGroupPks,
        app_names: targetAppNames,
      });
      setCreatedInvite(res);
    } catch (err: any) {
      setError(err.message || 'Failed to generate invitation link.');
    } finally {
      setLoading(false);
    }
  };

  const handleCopyLink = () => {
    if (!createdInvite) return;
    navigator.clipboard.writeText(createdInvite.invite_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const handleReset = () => {
    setName('');
    setEmail('');
    setPhone('');
    setSendViaWhatsapp(false);
    setExpiresInDays(7);
    setSingleUse(true);
    setSelectedApps({});
    setCreatedInvite(null);
    setError(null);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        
        {/* Modal Header */}
        <div className="p-5 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="h-9 w-9 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center">
              <UserPlus className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Create User Invitation</h3>
              <p className="text-xs text-slate-400">
                Generate an Authentik invite link with pre-assigned service access.
              </p>
            </div>
          </div>
          <button
            onClick={handleReset}
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Modal Content */}
        <div className="p-5 overflow-y-auto flex-1 space-y-4">
          
          {error && (
            <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs">
              {error}
            </div>
          )}

          {createdInvite ? (
            /* Success View: Display generated link */
            <div className="space-y-4 text-center py-2">
              <div className="h-12 w-12 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 mx-auto flex items-center justify-center">
                <Check className="h-6 w-6" />
              </div>
              <div>
                <h4 className="text-base font-semibold text-white">Invitation Link Created!</h4>
                <p className="text-xs text-slate-400 mt-1">
                  Send this link to <span className="text-indigo-400 font-medium">{createdInvite.name}</span>.
                  Once they sign up, they will automatically receive access to their pre-configured services.
                </p>
              </div>

              {/* URL Box */}
              <div className="bg-slate-950 border border-slate-800 rounded-xl p-3 flex items-center justify-between text-left">
                <div className="truncate mr-2 font-mono text-xs text-slate-300">
                  {createdInvite.invite_url}
                </div>
                <button
                  onClick={handleCopyLink}
                  className="flex items-center space-x-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs px-3 py-1.5 rounded-lg shadow transition-colors flex-shrink-0"
                >
                  {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  <span>{copied ? 'Copied!' : 'Copy'}</span>
                </button>
              </div>

              {/* WhatsApp Delivery Status or Quick Share */}
              {createdInvite.phone && (
                <div className="bg-emerald-950/20 border border-emerald-500/30 rounded-xl p-3 text-left flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <MessageSquare className="h-4 w-4 text-emerald-400" />
                    <span className="text-xs text-slate-300">
                      {createdInvite.whatsapp_sent ? (
                        <span className="text-emerald-300 font-medium">✓ Sent automatically via WhatsApp</span>
                      ) : (
                        <span>WhatsApp share link ready</span>
                      )}
                    </span>
                  </div>
                  <a
                    href={`https://wa.me/${createdInvite.phone.replace(/[^\d]/g, '')}?text=${encodeURIComponent(
                      `👋 Hi ${createdInvite.name}! Here is your personal access link to our home services (${createdInvite.assigned_apps.join(', ')}): ${createdInvite.invite_url}`
                    )}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center space-x-1 text-xs text-emerald-400 hover:text-emerald-300 font-semibold underline"
                  >
                    <span>Open WhatsApp</span>
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              )}

              {/* Pre-assigned Apps Summary */}
              {createdInvite.assigned_apps.length > 0 && (
                <div className="text-left bg-slate-950/50 border border-slate-800/80 rounded-xl p-3">
                  <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
                    Pre-Assigned Services ({createdInvite.assigned_apps.length})
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {createdInvite.assigned_apps.map((app) => (
                      <span
                        key={app}
                        className="px-2.5 py-1 rounded-md text-xs font-medium bg-indigo-500/10 text-indigo-300 border border-indigo-500/20"
                      >
                        {app}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div className="pt-2">
                <button
                  onClick={handleReset}
                  className="w-full bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium py-2 rounded-xl border border-slate-700 transition-colors"
                >
                  Done
                </button>
              </div>
            </div>
          ) : (
            /* Creation Form */
            <form onSubmit={handleSubmit} className="space-y-4">
              
              {/* Recipient Name */}
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Recipient Name / Label <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. John Doe (Brother) or Family Guest"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  required
                />
              </div>

              {/* Recipient Email & WhatsApp in 2 columns */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Email Address (Optional)
                  </label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-500" />
                    <input
                      type="email"
                      placeholder="john@example.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    WhatsApp / Mobile Number
                  </label>
                  <div className="relative">
                    <MessageSquare className="absolute left-3 top-2.5 h-3.5 w-3.5 text-emerald-500" />
                    <input
                      type="text"
                      placeholder="+44 7123 456789"
                      value={phone}
                      onChange={(e) => {
                        setPhone(e.target.value);
                        if (e.target.value.trim() && isWhatsAppConnected) {
                          setSendViaWhatsapp(true);
                        }
                      }}
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                </div>
              </div>

              {/* WhatsApp Auto-send toggle */}
              {phone && (
                <div className="p-3 bg-emerald-950/20 border border-emerald-500/30 rounded-xl">
                  <label className="flex items-center space-x-2.5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={sendViaWhatsapp}
                      onChange={(e) => setSendViaWhatsapp(e.target.checked)}
                      className="rounded border-slate-800 text-emerald-600 focus:ring-emerald-500 h-4 w-4 bg-slate-950"
                    />
                    <div className="text-xs">
                      <span className="font-semibold text-slate-200">Send invite link directly via WhatsApp</span>
                      <p className="text-[11px] text-slate-400">
                        {isWhatsAppConnected
                          ? 'Will be sent automatically through your paired WhatsApp device.'
                          : 'WhatsApp device not paired yet. Quick share link will be provided.'}
                      </p>
                    </div>
                  </label>
                </div>
              )}

              {/* Expiration & Single Use */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Expires In
                  </label>
                  <select
                    value={expiresInDays}
                    onChange={(e) => setExpiresInDays(Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-800 text-slate-300 text-xs rounded-xl px-3 py-2 focus:outline-none focus:border-indigo-500"
                  >
                    <option value={1}>24 Hours</option>
                    <option value={3}>3 Days</option>
                    <option value={7}>7 Days (Default)</option>
                    <option value={30}>30 Days</option>
                    <option value={0}>Never Expire</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Usage Limits
                  </label>
                  <label className="flex items-center space-x-2 mt-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={singleUse}
                      onChange={(e) => setSingleUse(e.target.checked)}
                      className="rounded border-slate-800 text-indigo-600 focus:ring-indigo-500 h-4 w-4 bg-slate-950"
                    />
                    <span className="text-xs text-slate-300">Single-use token</span>
                  </label>
                </div>
              </div>

              {/* Pre-assigned Applications Checkboxes */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-semibold text-slate-300">
                    Pre-Assign Access to Applications:
                  </label>
                  <div className="space-x-2 text-[11px]">
                    <button
                      type="button"
                      onClick={handleSelectAll}
                      className="text-indigo-400 hover:text-indigo-300 font-medium"
                    >
                      Select All
                    </button>
                    <span className="text-slate-600">•</span>
                    <button
                      type="button"
                      onClick={handleClearAll}
                      className="text-slate-400 hover:text-slate-300"
                    >
                      Clear
                    </button>
                  </div>
                </div>

                <div className="bg-slate-950 border border-slate-800 rounded-xl p-2.5 max-h-48 overflow-y-auto space-y-1.5 divide-y divide-slate-800/60">
                  {apps.map((app) => {
                    const isChecked = !!selectedApps[app.pk];
                    return (
                      <label
                        key={app.pk}
                        className={`flex items-center justify-between p-2 rounded-lg cursor-pointer transition-colors ${
                          isChecked ? 'bg-indigo-600/10 border border-indigo-500/20' : 'hover:bg-slate-900'
                        }`}
                      >
                        <div className="flex items-center space-x-2.5">
                          {app.meta_icon ? (
                            <img
                              src={app.meta_icon}
                              alt={app.name}
                              className="h-6 w-6 rounded object-contain bg-slate-900 p-0.5"
                            />
                          ) : (
                            <div className="h-6 w-6 rounded bg-indigo-500/10 text-indigo-400 flex items-center justify-center font-bold text-[10px]">
                              {app.name.substring(0, 2).toUpperCase()}
                            </div>
                          )}
                          <span className="text-xs font-medium text-slate-200">{app.name}</span>
                        </div>
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => handleToggleApp(app.pk)}
                          className="rounded border-slate-800 text-indigo-600 focus:ring-indigo-500 h-4 w-4 bg-slate-950"
                        />
                      </label>
                    );
                  })}
                </div>
              </div>

              {/* Submit Button */}
              <div className="pt-2">
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full flex items-center justify-center space-x-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold py-2.5 rounded-xl shadow-lg shadow-indigo-600/20 transition-all"
                >
                  <Link className="h-4 w-4" />
                  <span>{loading ? 'Generating Invite...' : 'Generate Invite Link'}</span>
                </button>
              </div>

            </form>
          )}

        </div>

      </div>
    </div>
  );
};
