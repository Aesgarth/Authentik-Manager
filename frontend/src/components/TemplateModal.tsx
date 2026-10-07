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
  Sparkles,
  Pencil,
  Search
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
  onUpdateTemplate: (templateId: number, params: {
    name?: string;
    description?: string;
    icon?: string;
    assignments?: Record<string, string>;
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
  onUpdateTemplate,
  onDeleteTemplate,
  onApplyTemplate,
  loading,
}) => {
  const [isCreating, setIsCreating] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<AccessTemplate | null>(null);
  const [selectedTemplateForApply, setSelectedTemplateForApply] = useState<AccessTemplate | null>(null);
  const [selectedUserPk, setSelectedUserPk] = useState<number | null>(null);
  const [durationHours, setDurationHours] = useState<number | undefined>(undefined);

  // Template Form State (used for both create and edit)
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newIcon, setNewIcon] = useState('shield');
  const [newAssignments, setNewAssignments] = useState<Record<string, string>>({});
  const [appSearch, setAppSearch] = useState('');
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const isFormOpen = isCreating || editingTemplate !== null;

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

  const handleStartCreate = () => {
    setEditingTemplate(null);
    setIsCreating(true);
    setNewName('');
    setNewDescription('');
    setNewIcon('shield');
    setNewAssignments({});
    setAppSearch('');
    setError(null);
    setSelectedTemplateForApply(null);
  };

  const handleStartEdit = (tpl: AccessTemplate) => {
    setIsCreating(false);
    setEditingTemplate(tpl);
    setNewName(tpl.name);
    setNewDescription(tpl.description || '');
    setNewIcon(tpl.icon || 'shield');

    // Normalize assignments to app.pk:
    // 1. Strip known obsolete dummy keys (e.g. 'guest-wifi').
    // 2. If a key is an app slug, resolve it to canonical app.pk so it doesn't duplicate app.pk.
    // 3. Keep '*' wildcard and any unmatched keys for user visibility and removal.
    const normalized: Record<string, string> = {};
    Object.entries(tpl.assignments || {}).forEach(([key, role]) => {
      if (key === 'guest-wifi') return;
      if (key === '*') {
        normalized['*'] = role;
        return;
      }
      const appByPk = apps.find((a) => a.pk === key);
      if (appByPk) {
        normalized[appByPk.pk] = role;
        return;
      }
      const appBySlug = apps.find((a) => a.slug && a.slug.toLowerCase() === key.toLowerCase());
      if (appBySlug) {
        normalized[appBySlug.pk] = role;
        return;
      }
      normalized[key] = role;
    });

    setNewAssignments(normalized);
    setAppSearch('');
    setError(null);
    setSelectedTemplateForApply(null);
  };

  const handleCancelForm = () => {
    setIsCreating(false);
    setEditingTemplate(null);
    setNewName('');
    setNewDescription('');
    setNewAssignments({});
    setAppSearch('');
    setError(null);
  };

  const handleSetAllRoles = (role: 'member' | 'admin' | 'none') => {
    if (role === 'none') {
      setNewAssignments({});
      return;
    }
    const updated: Record<string, string> = {};
    apps.forEach((a) => {
      updated[a.pk] = role;
    });
    setNewAssignments(updated);
  };

  const handleFormSubmit = async (e: React.FormEvent) => {
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
      if (editingTemplate) {
        await onUpdateTemplate(editingTemplate.id, {
          name: newName.trim(),
          description: newDescription.trim() || undefined,
          icon: newIcon,
          assignments: newAssignments,
        });
      } else {
        await onCreateTemplate({
          name: newName.trim(),
          description: newDescription.trim() || undefined,
          icon: newIcon,
          assignments: newAssignments,
        });
      }
      handleCancelForm();
    } catch (err: any) {
      setError(err.message || (editingTemplate ? 'Failed to update preset' : 'Failed to create preset'));
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

  const filteredApps = apps.filter(
    (a) =>
      a.name.toLowerCase().includes(appSearch.toLowerCase()) ||
      (a.slug && a.slug.toLowerCase().includes(appSearch.toLowerCase()))
  );

  const activeAssignmentCount = Object.keys(newAssignments).length;

  // Identify any keys in newAssignments that don't match any known application (excluding wildcard)
  const unmatchedKeys = Object.keys(newAssignments).filter(
    (k) =>
      k !== '*' &&
      !apps.some((a) => a.pk === k || (a.slug && a.slug.toLowerCase() === k.toLowerCase()))
  );

  // Helper to extract unique display items for template cards, avoiding duplicates from slug vs pk
  const getTemplateDisplayItems = (assignments: Record<string, string>) => {
    const seenPks = new Set<string>();
    const items: { key: string; name: string; role: string; isOrphan: boolean }[] = [];

    Object.entries(assignments || {}).forEach(([key, role]) => {
      if (key === '*') return;
      if (key === 'guest-wifi') return; // Ignore legacy dummy key

      const appByPk = apps.find((a) => a.pk === key);
      if (appByPk) {
        if (!seenPks.has(appByPk.pk)) {
          seenPks.add(appByPk.pk);
          items.push({ key: appByPk.pk, name: appByPk.name, role, isOrphan: false });
        }
        return;
      }

      const appBySlug = apps.find((a) => a.slug && a.slug.toLowerCase() === key.toLowerCase());
      if (appBySlug) {
        if (!seenPks.has(appBySlug.pk)) {
          seenPks.add(appBySlug.pk);
          items.push({ key: appBySlug.pk, name: appBySlug.name, role, isOrphan: false });
        }
        return;
      }

      items.push({ key, name: key, role, isOrphan: true });
    });

    return items;
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
            {!isFormOpen && (
              <button
                type="button"
                onClick={handleStartCreate}
                className="flex items-center space-x-1.5 bg-[#fd7e14] hover:bg-[#ea6c0a] text-white text-xs font-semibold px-3 py-1.5 rounded-lg shadow-sm transition-colors cursor-pointer"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>New Preset</span>
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-white hover:bg-[#1e2c3f] rounded-lg transition-colors cursor-pointer"
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

          {/* Create or Edit Preset Form */}
          {isFormOpen && (
            <form onSubmit={handleFormSubmit} className="space-y-4 bg-[#0b0f17] border border-[#25354b] p-4 rounded-xl animate-in fade-in slide-in-from-top-2 duration-200">
              <div className="flex items-center justify-between pb-2 border-b border-[#25354b]">
                <div className="flex items-center space-x-2">
                  {editingTemplate ? <Pencil className="h-4 w-4 text-[#fd7e14]" /> : <Plus className="h-4 w-4 text-[#fd7e14]" />}
                  <h4 className="text-xs font-bold text-white uppercase tracking-wider">
                    {editingTemplate ? `Edit Access Preset: ${editingTemplate.name}` : 'Create Access Preset'}
                  </h4>
                </div>
                <button
                  type="button"
                  onClick={handleCancelForm}
                  className="text-xs text-slate-400 hover:text-white cursor-pointer"
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
                    autoFocus
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

              {/* Service Role Assignments Box */}
              <div className="space-y-2">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <label className="block text-xs font-semibold text-slate-300">
                    Service Role Assignments ({activeAssignmentCount} configured):
                  </label>
                  
                  {/* Quick Batch Selectors */}
                  <div className="flex items-center gap-1.5 self-end sm:self-auto">
                    <span className="text-[10px] text-slate-500 mr-1">Batch:</span>
                    <button
                      type="button"
                      onClick={() => handleSetAllRoles('member')}
                      className="px-2 py-0.5 rounded bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/25 text-[10px] font-medium transition-colors cursor-pointer"
                    >
                      All Member
                    </button>
                    <button
                      type="button"
                      onClick={() => handleSetAllRoles('admin')}
                      className="px-2 py-0.5 rounded bg-orange-500/10 hover:bg-orange-500/20 text-orange-300 border border-orange-500/25 text-[10px] font-medium transition-colors cursor-pointer"
                    >
                      All Admin
                    </button>
                    <button
                      type="button"
                      onClick={() => handleSetAllRoles('none')}
                      className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 text-[10px] font-medium transition-colors cursor-pointer"
                    >
                      Clear All
                    </button>
                  </div>
                </div>

                {/* Filter / Search Bar if many apps */}
                {apps.length > 5 && (
                  <div className="relative">
                    <Search className="h-3.5 w-3.5 text-slate-500 absolute left-3 top-2.5" />
                    <input
                      type="text"
                      placeholder="Filter applications by name..."
                      value={appSearch}
                      onChange={(e) => setAppSearch(e.target.value)}
                      className="w-full bg-[#111827] border border-[#25354b] rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-[#fd7e14]"
                    />
                  </div>
                )}

                {/* Wildcard Rule Banner (Optional Master Rule) */}
                <div className="flex items-center justify-between p-2.5 bg-orange-500/10 border border-orange-500/20 rounded-xl">
                  <div className="flex items-center space-x-2">
                    <Sparkles className="h-4 w-4 text-[#fd7e14] shrink-0" />
                    <div>
                      <span className="text-xs text-white font-semibold">Master Rule: All Services (*)</span>
                      <p className="text-[10px] text-slate-400">Defaults all current & future applications unless overridden below.</p>
                    </div>
                  </div>
                  <div className="flex items-center space-x-1 shrink-0">
                    {(['none', 'member', 'admin'] as const).map((r) => {
                      const isCurrent = (newAssignments['*'] || 'none') === r;
                      return (
                        <button
                          key={r}
                          type="button"
                          onClick={() => {
                            setNewAssignments((prev) => {
                              const updated = { ...prev };
                              if (r === 'none') {
                                delete updated['*'];
                              } else {
                                updated['*'] = r;
                              }
                              return updated;
                            });
                          }}
                          className={`px-2 py-0.5 rounded text-[11px] font-medium capitalize transition-all cursor-pointer ${
                            isCurrent
                              ? r === 'admin'
                                ? 'bg-orange-500 text-white font-bold shadow'
                                : r === 'member'
                                ? 'bg-emerald-500 text-white font-bold shadow'
                                : 'bg-slate-700 text-white'
                              : 'text-slate-400 hover:text-white'
                          }`}
                        >
                          {r}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Unmatched / Legacy Services Banner (if any orphaned keys exist) */}
                {unmatchedKeys.length > 0 && (
                  <div className="p-3 bg-amber-500/10 border border-amber-500/25 rounded-xl space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-amber-300 font-semibold flex items-center gap-1.5">
                        <span>⚠️ Unmatched Services ({unmatchedKeys.length})</span>
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          setNewAssignments((prev) => {
                            const updated = { ...prev };
                            unmatchedKeys.forEach((k) => delete updated[k]);
                            return updated;
                          });
                        }}
                        className="text-[11px] text-amber-400 hover:text-white underline cursor-pointer font-medium"
                      >
                        Remove All Unmatched
                      </button>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      These services exist in this preset but do not match any currently known Authentik applications:
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {unmatchedKeys.map((k) => (
                        <span
                          key={k}
                          className="inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded bg-[#16202e] text-amber-200 border border-amber-500/30 font-mono"
                        >
                          <span>{k} ({newAssignments[k]})</span>
                          <button
                            type="button"
                            onClick={() => {
                              setNewAssignments((prev) => {
                                const updated = { ...prev };
                                delete updated[k];
                                return updated;
                              });
                            }}
                            className="text-slate-400 hover:text-white hover:bg-slate-700 rounded p-0.5 transition-colors cursor-pointer"
                            title={`Remove ${k}`}
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Per-Application List */}
                <div className="bg-[#111827] border border-[#25354b] rounded-xl p-2.5 max-h-52 overflow-y-auto space-y-1 divide-y divide-[#25354b]/50">
                  {filteredApps.length === 0 ? (
                    <div className="text-center py-4 text-xs text-slate-500">
                      No applications match "{appSearch}"
                    </div>
                  ) : (
                    filteredApps.map((app) => {
                      const currentRole = newAssignments[app.pk] || (app.slug ? newAssignments[app.slug] : undefined) || 'none';
                      return (
                        <div key={app.pk} className="flex items-center justify-between p-2">
                          <div className="flex items-center space-x-2 truncate">
                            {app.meta_icon ? (
                              <img src={app.meta_icon} alt={app.name} className="h-5 w-5 object-contain shrink-0" />
                            ) : (
                              <div className="h-5 w-5 rounded bg-[#1e2c3f] text-[#fd7e14] text-[9px] flex items-center justify-center font-bold shrink-0">
                                {app.name.substring(0, 2).toUpperCase()}
                              </div>
                            )}
                            <span className="text-xs text-slate-200 font-medium truncate">{app.name}</span>
                          </div>

                          <div className="flex items-center space-x-1 shrink-0">
                            {(['none', 'member', 'admin'] as const).map((r) => (
                              <button
                                key={r}
                                type="button"
                                onClick={() => {
                                  setNewAssignments((prev) => {
                                    const updated = { ...prev };
                                    delete updated[app.pk];
                                    if (app.slug) {
                                      delete updated[app.slug];
                                    }
                                    if (r !== 'none') {
                                      updated[app.pk] = r;
                                    }
                                    return updated;
                                  });
                                }}
                                className={`px-2 py-0.5 rounded text-[11px] font-medium capitalize transition-all cursor-pointer ${
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
                    })
                  )}
                </div>
              </div>

              <div className="flex justify-end space-x-2 pt-2 border-t border-[#25354b]">
                <button
                  type="button"
                  onClick={handleCancelForm}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="bg-[#fd7e14] hover:bg-[#ea6c0a] disabled:opacity-50 text-white text-xs font-semibold px-4 py-1.5 rounded-lg shadow-sm transition-colors cursor-pointer flex items-center gap-1.5"
                >
                  {editingTemplate && <Pencil className="h-3 w-3" />}
                  <span>{editingTemplate ? 'Save Changes' : 'Save Preset'}</span>
                </button>
              </div>
            </form>
          )}

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
                  type="button"
                  onClick={() => setSelectedTemplateForApply(null)}
                  className="text-slate-400 hover:text-white text-xs cursor-pointer"
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
                    className="flex items-center space-x-1.5 bg-[#fd7e14] hover:bg-[#ea6c0a] disabled:opacity-50 text-white text-xs font-semibold px-4 py-2 rounded-lg shadow-sm transition-colors cursor-pointer"
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
              const isWildcard = !!tpl.assignments['*'];
              const displayItems = getTemplateDisplayItems(tpl.assignments);
              const isBeingEdited = editingTemplate?.id === tpl.id;

              return (
                <div
                  key={tpl.id}
                  className={`rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 transition-all ${
                    isBeingEdited
                      ? 'bg-orange-500/10 border-2 border-orange-500/70 shadow-lg'
                      : 'bg-[#0b0f17] border border-[#25354b] hover:border-[#2c3f58]'
                  }`}
                >
                  <div className="flex items-start space-x-3.5">
                    <div className="h-10 w-10 rounded-xl bg-[#16202e] border border-[#25354b] flex items-center justify-center shrink-0">
                      {getTemplateIcon(tpl.icon)}
                    </div>
                    <div>
                      <div className="flex items-center space-x-2">
                        <h4 className="text-sm font-semibold text-white">{tpl.name}</h4>
                        <span className="text-[10px] text-slate-400 bg-[#16202e] px-2 py-0.5 rounded border border-[#25354b]">
                          {isWildcard ? 'All Applications' : `${displayItems.length} Services`}
                        </span>
                        {isBeingEdited && (
                          <span className="text-[10px] font-semibold text-orange-400 bg-orange-500/20 px-2 py-0.5 rounded border border-orange-500/30">
                            Editing
                          </span>
                        )}
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
                          displayItems.slice(0, 5).map((item) => (
                            <span
                              key={item.key}
                              className={`text-[10px] px-2 py-0.5 rounded font-medium ${
                                item.role === 'admin'
                                  ? 'bg-orange-500/10 text-[#fd7e14] border border-orange-500/20'
                                  : item.isOrphan
                                  ? 'bg-amber-500/10 text-amber-300 border border-amber-500/20'
                                  : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                              }`}
                            >
                              {item.name} ({item.role})
                            </span>
                          ))
                        )}
                        {!isWildcard && displayItems.length > 5 && (
                          <span className="text-[10px] text-slate-500 self-center">
                            +{displayItems.length - 5} more
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center space-x-1.5 self-end sm:self-center shrink-0">
                    {/* Edit Preset Button */}
                    <button
                      type="button"
                      onClick={() => handleStartEdit(tpl)}
                      className={`flex items-center space-x-1.5 text-xs px-2.5 py-1.5 rounded-lg border transition-all cursor-pointer ${
                        isBeingEdited
                          ? 'bg-orange-500 text-white border-orange-500 shadow'
                          : 'bg-[#16202e] hover:bg-slate-700 text-slate-200 hover:text-white border-[#25354b] hover:border-slate-500'
                      }`}
                      title="Edit this preset's name, icon, and application permissions"
                    >
                      <Pencil className="h-3.5 w-3.5 text-[#fd7e14]" />
                      <span>Edit</span>
                    </button>

                    {/* Apply to User Button */}
                    <button
                      type="button"
                      onClick={() => setSelectedTemplateForApply(tpl)}
                      className="flex items-center space-x-1.5 bg-[#16202e] hover:bg-[#fd7e14] text-slate-200 hover:text-white text-xs px-3 py-1.5 rounded-lg border border-[#25354b] hover:border-[#fd7e14] transition-all cursor-pointer"
                    >
                      <Users className="h-3.5 w-3.5" />
                      <span>Apply...</span>
                    </button>

                    {/* Delete Custom Preset Button */}
                    {tpl.id > 3 && (
                      <button
                        type="button"
                        onClick={() => onDeleteTemplate(tpl.id)}
                        className="p-1.5 text-slate-500 hover:text-rose-400 hover:bg-rose-950/40 rounded-lg transition-colors cursor-pointer"
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
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-xs font-medium text-slate-300 hover:bg-[#1e2c3f] transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>

      </div>
    </div>
  );
};
