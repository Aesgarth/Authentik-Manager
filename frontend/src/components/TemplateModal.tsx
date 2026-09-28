import React, { useState } from 'react';
import { 
  X, 
  Shield, 
  Home, 
  Users, 
  Crown, 
  Film, 
  Plus, 
  Trash2, 
  ArrowRight,
  Sparkles
} from 'lucide-react';
import { AccessTemplate, Application, User } from '../types';

interface TemplateModalProps {
  isOpen: boolean;
  onClose: () => void;
  templates: AccessTemplate[];
  apps: Application[];
  users: User[];
  onCreateTemplate: (params: {
    name: string;
    description?: string;
    icon?: string;
    assignments: Record<string, string>;
  }) => Promise<void>;
  onDeleteTemplate: (templateId: number) => Promise<void>;
  onApplyTemplate: (templateId: number, params: {
    user_pk: number;
    user_name: string;
    duration_hours?: number;
  }) => Promise<void>;
  loading: boolean;
}

export const TemplateModal: React.FC<TemplateModalProps> = ({
  isOpen,
  onClose,
  templates,
  apps,
  users,
  onCreateTemplate,
  onDeleteTemplate,
  onApplyTemplate,
  loading,
}) => {
  const [isCreating, setIsCreating] = useState(false);
  const [selectedTemplateForApply, setSelectedTemplateForApply] = useState<AccessTemplate | null>(null);
  const [selectedUserPk, setSelectedUserPk] = useState<number | null>(null);
  const [durationHours, setDurationHours] = useState<number | undefined>(undefined);

  // New Template Form State
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newIcon, setNewIcon] = useState('shield');
  const [newAssignments, setNewAssignments] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const getTemplateIcon = (iconName: string) => {
    switch (iconName) {
      case 'home':
        return <Home className="h-5 w-5 text-[#fd7e14]" />;
      case 'users':
        return <Users className="h-5 w-5 text-emerald-400" />;
      case 'crown':
        return <Crown className="h-5 w-5 text-amber-400" />;
      case 'film':
        return <Film className="h-5 w-5 text-sky-400" />;
      default:
        return <Shield className="h-5 w-5 text-[#fd7e14]" />;
    }
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) {
      setError('Please provide a name for the access preset');
      return;
    }
    if (Object.keys(newAssignments).length === 0) {
      setError('Please configure access for at least one application');
      return;
    }

    try {
      setError(null);
      await onCreateTemplate({
        name: newName.trim(),
        description: newDescription.trim() || undefined,
        icon: newIcon,
        assignments: newAssignments,
      });
      setIsCreating(false);
      setNewName('');
      setNewDescription('');
      setNewAssignments({});
    } catch (err: any) {
      setError(err.message || 'Failed to create template');
    }
  };

  const handleApplySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedTemplateForApply || !selectedUserPk) return;
    const targetUser = users.find((u) => u.pk === selectedUserPk);
    if (!targetUser) return;

    try {
      setError(null);
      await onApplyTemplate(selectedTemplateForApply.id, {
        user_pk: targetUser.pk,
        user_name: targetUser.name,
        duration_hours: durationHours,
      });
      setSelectedTemplateForApply(null);
      setSelectedUserPk(null);
      setDurationHours(undefined);
    } catch (err: any) {
      setError(err.message || 'Failed to apply preset');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in">
      <div className="bg-[#111827] border border-[#25354b] rounded-2xl w-full max-w-3xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        
        {/* Header */}
        <div className="p-5 border-b border-[#25354b] bg-[#16202e] flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="h-9 w-9 rounded-lg bg-orange-500/15 border border-orange-500/30 text-[#fd7e14] flex items-center justify-center">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <span>Access Personas & Role Presets</span>
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-orange-500/10 text-[#fd7e14] border border-orange-500/20">
                  {templates.length} Active Presets
                </span>
              </h3>
              <p className="text-xs text-slate-400">
                1-click bundle application memberships and guest leases for users and invitations.
              </p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            {!isCreating && (
              <button
                onClick={() => setIsCreating(true)}
                className="flex items-center space-x-1.5 bg-[#fd7e14] hover:bg-[#ea6c0a] text-white text-xs font-semibold px-3 py-1.5 rounded-lg shadow-sm transition-colors"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>New Preset</span>
              </button>
            )}
            <button
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-white hover:bg-[#1e2c3f] rounded-lg transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-5 overflow-y-auto flex-1 space-y-4">
          
          {error && (
            <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs">
              {error}
            </div>
          )}

          {/* Create Preset Form */}
          {isCreating ? (
            <form onSubmit={handleCreateSubmit} className="space-y-4 bg-[#0b0f17] border border-[#25354b] p-4 rounded-xl">
              <div className="flex items-center justify-between pb-2 border-b border-[#25354b]">
                <h4 className="text-xs font-bold text-white uppercase tracking-wider">
                  Create Access Preset
                </h4>
                <button
                  type="button"
                  onClick={() => setIsCreating(false)}
                  className="text-xs text-slate-400 hover:text-white"
                >
                  Cancel
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="sm:col-span-2">
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Preset Name <span className="text-rose-400">*</span>
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Media Streamer, Roommate, Contractor"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    className="w-full bg-[#111827] border border-[#25354b] rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-[#fd7e14]"
                    required
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Icon</label>
                  <select
                    value={newIcon}
                    onChange={(e) => setNewIcon(e.target.value)}
                    className="w-full bg-[#111827] border border-[#25354b] rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-[#fd7e14]"
                  >
                    <option value="shield">🛡️ Shield (Default)</option>
                    <option value="home">🏠 Home / Family</option>
                    <option value="users">👥 Guest / Visitor</option>
                    <option value="film">🎬 Media / Streaming</option>
                    <option value="crown">👑 Administrator</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Description
                </label>
                <input
                  type="text"
                  placeholder="Summary of this persona's permissions..."
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  className="w-full bg-[#111827] border border-[#25354b] rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-[#fd7e14]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-2">
                  Service Role Assignments:
                </label>
                <div className="bg-[#111827] border border-[#25354b] rounded-xl p-2.5 max-h-48 overflow-y-auto space-y-1 divide-y divide-[#25354b]/50">
                  {apps.map((app) => {
                    const currentRole = newAssignments[app.pk] || 'none';
                    return (
                      <div key={app.pk} className="flex items-center justify-between p-2">
                        <div className="flex items-center space-x-2">
                          {app.meta_icon ? (
                            <img src={app.meta_icon} alt={app.name} className="h-5 w-5 object-contain" />
                          ) : (
                            <div className="h-5 w-5 rounded bg-[#1e2c3f] text-[#fd7e14] text-[9px] flex items-center justify-center font-bold">
                              {app.name.substring(0, 2).toUpperCase()}
                            </div>
                          )}
                          <span className="text-xs text-slate-200 font-medium">{app.name}</span>
                        </div>

                        <div className="flex items-center space-x-1">
                          {(['none', 'member', 'admin'] as const).map((r) => (
                            <button
                              key={r}
                              type="button"
                              onClick={() => {
                                setNewAssignments((prev) => {
                                  const updated = { ...prev };
                                  if (r === 'none') {
                                    delete updated[app.pk];
                                  } else {
                                    updated[app.pk] = r;
                                  }
                                  return updated;
                                });
                              }}
                              className={`px-2 py-0.5 rounded text-[11px] font-medium capitalize transition-all ${
                                currentRole === r
                                  ? r === 'admin'
                                    ? 'bg-orange-500/20 text-[#fd7e14] border border-orange-500/30'
                                    : r === 'member'
                                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                                    : 'bg-[#1e2c3f] text-slate-300 border border-[#2c3f58]'
                                  : 'text-slate-500 hover:text-slate-300'
                              }`}
                            >
                              {r}
                            </button>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="flex justify-end space-x-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsCreating(false)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="bg-[#fd7e14] hover:bg-[#ea6c0a] text-white text-xs font-semibold px-4 py-1.5 rounded-lg shadow-sm transition-colors"
                >
                  Save Preset
                </button>
              </div>
            </form>
          ) : null}

          {/* Quick Apply Panel (if a template is selected) */}
          {selectedTemplateForApply && (
            <div className="bg-[#16202e] border border-orange-500/30 rounded-xl p-4 animate-in fade-in space-y-3">
              <div className="flex items-center justify-between pb-2 border-b border-[#25354b]">
                <div className="flex items-center space-x-2">
                  {getTemplateIcon(selectedTemplateForApply.icon)}
                  <h4 className="text-xs font-bold text-white">
                    Apply "{selectedTemplateForApply.name}" to User
                  </h4>
                </div>
                <button
                  onClick={() => setSelectedTemplateForApply(null)}
                  className="text-slate-400 hover:text-white text-xs"
                >
                  ✕
                </button>
              </div>

              <form onSubmit={handleApplySubmit} className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">
                      Target User <span className="text-rose-400">*</span>
                    </label>
                    <select
                      value={selectedUserPk || ''}
                      onChange={(e) => setSelectedUserPk(Number(e.target.value))}
                      className="w-full bg-[#0b0f17] border border-[#25354b] rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-[#fd7e14]"
                      required
                    >
                      <option value="">-- Choose User --</option>
                      {users.map((u) => (
                        <option key={u.pk} value={u.pk}>
                          {u.name} (@{u.username})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">
                      Access Duration (Optional Lease)
                    </label>
                    <select
                      value={durationHours || ''}
                      onChange={(e) => setDurationHours(e.target.value ? Number(e.target.value) : undefined)}
                      className="w-full bg-[#0b0f17] border border-[#25354b] rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-[#fd7e14]"
                    >
                      <option value="">Permanent (No Expiration)</option>
                      <option value="24">24 Hours (Guest Pass)</option>
                      <option value="72">3 Days (Weekend Pass)</option>
                      <option value="168">7 Days (1 Week)</option>
                      <option value="720">30 Days (1 Month)</option>
                    </select>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-1">
                  <span className="text-[11px] text-slate-400">
                    Will batch-assign all pre-configured application memberships to this user.
                  </span>
                  <button
                    type="submit"
                    disabled={loading || !selectedUserPk}
                    className="flex items-center space-x-1.5 bg-[#fd7e14] hover:bg-[#ea6c0a] disabled:opacity-50 text-white text-xs font-semibold px-4 py-2 rounded-lg shadow-sm transition-colors"
                  >
                    <span>Execute Batch Assignment</span>
                    <ArrowRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* List of Templates */}
          <div className="space-y-3">
            {templates.map((tpl) => {
              const assignmentKeys = Object.keys(tpl.assignments);
              const isWildcard = tpl.assignments['*'];

              return (
                <div
                  key={tpl.id}
                  className="bg-[#0b0f17] border border-[#25354b] hover:border-[#2c3f58] rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 transition-colors"
                >
                  <div className="flex items-start space-x-3.5">
                    <div className="h-10 w-10 rounded-xl bg-[#16202e] border border-[#25354b] flex items-center justify-center shrink-0">
                      {getTemplateIcon(tpl.icon)}
                    </div>
                    <div>
                      <div className="flex items-center space-x-2">
                        <h4 className="text-sm font-semibold text-white">{tpl.name}</h4>
                        <span className="text-[10px] text-slate-400 bg-[#16202e] px-2 py-0.5 rounded border border-[#25354b]">
                          {isWildcard ? 'All Applications' : `${assignmentKeys.length} Services`}
                        </span>
                      </div>
                      {tpl.description && (
                        <p className="text-xs text-slate-400 mt-0.5">{tpl.description}</p>
                      )}

                      {/* Apps preview pills */}
                      <div className="flex flex-wrap gap-1 mt-2">
                        {isWildcard ? (
                          <span className="text-[10px] px-2 py-0.5 rounded font-mono bg-orange-500/10 text-[#fd7e14] border border-orange-500/20">
                            * All Services ({tpl.assignments['*']})
                          </span>
                        ) : (
                          assignmentKeys.slice(0, 5).map((appPk) => {
                            const app = apps.find((a) => a.pk === appPk || a.slug === appPk);
                            const appName = app ? app.name : appPk;
                            const role = tpl.assignments[appPk];
                            return (
                              <span
                                key={appPk}
                                className={`text-[10px] px-2 py-0.5 rounded font-medium ${
                                  role === 'admin'
                                    ? 'bg-orange-500/10 text-[#fd7e14] border border-orange-500/20'
                                    : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                }`}
                              >
                                {appName} ({role})
                              </span>
                            );
                          })
                        )}
                        {!isWildcard && assignmentKeys.length > 5 && (
                          <span className="text-[10px] text-slate-500 self-center">
                            +{assignmentKeys.length - 5} more
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center space-x-2 self-end sm:self-center shrink-0">
                    <button
                      onClick={() => setSelectedTemplateForApply(tpl)}
                      className="flex items-center space-x-1.5 bg-[#16202e] hover:bg-[#fd7e14] text-slate-200 hover:text-white text-xs px-3 py-1.5 rounded-lg border border-[#25354b] hover:border-[#fd7e14] transition-all"
                    >
                      <Users className="h-3.5 w-3.5" />
                      <span>Apply to User...</span>
                    </button>

                    {tpl.id > 3 && (
                      <button
                        onClick={() => onDeleteTemplate(tpl.id)}
                        className="p-1.5 text-slate-500 hover:text-rose-400 hover:bg-rose-950/40 rounded-lg transition-colors"
                        title="Delete custom preset"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

        </div>

        {/* Footer */}
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
