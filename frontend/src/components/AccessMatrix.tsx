import React, { useState, useMemo, useRef, useEffect } from 'react';
import { 
  Search, 
  Check, 
  Lock, 
  UserCheck, 
  UserX,
  Crown,
  Sparkles,
  X,
  CheckCircle2,
  XCircle,
  Flag
} from 'lucide-react';
import { AccessMatrixData, User, Application, StagedChange } from '../types';

interface AccessMatrixProps {
  data: AccessMatrixData;
  stagedMode: boolean;
  stagedChanges: StagedChange[];
  onSetRole: (user: User, app: Application, newRole: 'none' | 'member' | 'admin') => void;
  onApplyStagedChanges: () => void;
  onDiscardStagedChanges: () => void;
  onToggleUserActive: (user_pk: number) => void;
  onProvisionApp: (app_pk: string) => void;
  onProvisionAll?: (options?: any) => Promise<any>;
  loading: boolean;
}

interface ActivePopover {
  user: User;
  app: Application;
  rect: DOMRect;
  currentRole: 'none' | 'member' | 'admin' | 'inherited';
  inheritedGroups: string[];
}

export const AccessMatrix: React.FC<AccessMatrixProps> = ({
  data,
  stagedMode,
  stagedChanges,
  onSetRole,
  onApplyStagedChanges,
  onDiscardStagedChanges,
  onToggleUserActive,
  onProvisionApp,
  onProvisionAll,
  loading,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [userFilter, setUserFilter] = useState<'all' | 'admin' | 'active' | 'inactive'>('all');
  const [provisioningAll, setProvisioningAll] = useState(false);
  const [popover, setPopover] = useState<ActivePopover | null>(null);

  const popoverRef = useRef<HTMLDivElement | null>(null);

  // Close popover on outside click or escape key
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setPopover(null);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPopover(null);
    };

    if (popover) {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [popover]);

  // Check how many apps lack granular groups
  const appsNeedingGranular = useMemo(() => {
    return data.apps.filter((a) => !a.has_granular_user_group);
  }, [data.apps]);

  // Compute unique app categories
  const categories = useMemo(() => {
    const set = new Set<string>();
    data.apps.forEach((a) => {
      if (a.group) set.add(a.group);
    });
    return Array.from(set);
  }, [data.apps]);

  // Filtered applications
  const filteredApps = useMemo(() => {
    return data.apps.filter((a) => {
      const matchesCategory = selectedCategory === 'all' || a.group === selectedCategory;
      const matchesSearch =
        a.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        a.slug.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesCategory && (searchQuery ? matchesSearch || true : true);
    });
  }, [data.apps, selectedCategory, searchQuery]);

  // Filtered users
  const filteredUsers = useMemo(() => {
    return data.users.filter((u) => {
      const q = searchQuery.toLowerCase();
      const matchesSearch =
        u.username.toLowerCase().includes(q) ||
        u.name.toLowerCase().includes(q) ||
        (u.email && u.email.toLowerCase().includes(q));

      if (userFilter === 'admin' && !u.is_superuser) return false;
      if (userFilter === 'active' && !u.is_active) return false;
      if (userFilter === 'inactive' && u.is_active) return false;

      return matchesSearch;
    });
  }, [data.users, searchQuery, userFilter]);

  // Fast staged change lookup: `${user_pk}-${app_pk}` -> StagedChange[]
  const stagedMap = useMemo(() => {
    const map = new Map<string, StagedChange[]>();
    stagedChanges.forEach((sc) => {
      const key = `${sc.user_pk}-${sc.app_pk}`;
      const list = map.get(key) || [];
      list.push(sc);
      map.set(key, list);
    });
    return map;
  }, [stagedChanges]);

  const handleQuickProvisionAll = async () => {
    if (!onProvisionAll) return;
    setProvisioningAll(true);
    try {
      await onProvisionAll({
        create_user_groups: true,
        create_admin_groups: true,
        include_already_secured: true,
      });
    } finally {
      setProvisioningAll(false);
    }
  };

  const handleCellClick = (
    e: React.MouseEvent<HTMLButtonElement>,
    user: User,
    app: Application,
    currentRole: 'none' | 'member' | 'admin' | 'inherited',
    inheritedGroups: string[]
  ) => {
    if (user.is_superuser) return;
    const rect = e.currentTarget.getBoundingClientRect();
    setPopover({
      user,
      app,
      rect,
      currentRole,
      inheritedGroups,
    });
  };

  const handleSelectRole = (newRole: 'none' | 'member' | 'admin') => {
    if (!popover) return;
    onSetRole(popover.user, popover.app, newRole);
    setPopover(null);
  };

  return (
    <div className="bg-[#111827] border border-[#25354b] rounded-2xl shadow-xl overflow-hidden flex flex-col">
      
      {/* 1-Click Granular RBAC Setup Callout (PatternFly Enterprise style) */}
      {appsNeedingGranular.length > 0 && onProvisionAll && (
        <div className="bg-[#16202e] border-b border-[#25354b] px-5 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
          <div className="flex items-center space-x-3 text-slate-300">
            <div className="h-8 w-8 rounded-lg bg-orange-500/15 text-[#fd7e14] border border-orange-500/30 flex items-center justify-center shrink-0">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <p className="font-semibold text-white flex items-center gap-1.5">
                <span>Granular Per-Service Groups Available</span>
                <span className="text-[11px] font-normal px-2 py-0.2 rounded-full bg-orange-500/10 text-[#fd7e14] border border-orange-500/20">
                  PatternFly RBAC
                </span>
              </p>
              <p className="text-[11px] text-slate-400 mt-0.5">
                {appsNeedingGranular.length} services currently rely on global groups. Set up individual Member & Admin groups with 1 click.
              </p>
            </div>
          </div>
          <button
            onClick={handleQuickProvisionAll}
            disabled={loading || provisioningAll}
            className="bg-[#fd7e14] hover:bg-[#ea6c0a] disabled:opacity-50 text-white font-semibold px-4 py-1.5 rounded-lg transition-all shadow-sm flex items-center justify-center gap-1.5 shrink-0"
          >
            <Sparkles className="h-3.5 w-3.5" />
            <span>{provisioningAll ? 'Configuring Groups...' : `Auto-Setup All (${appsNeedingGranular.length})`}</span>
          </button>
        </div>
      )}

      {/* Matrix Controls & Search Toolbar */}
      <div className="p-3.5 border-b border-[#25354b] bg-[#16202e]/60 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        
        {/* Search */}
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search users or applications..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-[#0b0f17] border border-[#25354b] rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-[#fd7e14] transition-colors"
          />
        </div>

        {/* Filter Pills */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Category Filter */}
          <div className="flex items-center space-x-1 overflow-x-auto py-0.5">
            <button
              onClick={() => setSelectedCategory('all')}
              className={`px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                selectedCategory === 'all'
                  ? 'bg-[#fd7e14] text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-[#1e2c3f]'
              }`}
            >
              All ({data.apps.length})
            </button>
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-all whitespace-nowrap ${
                  selectedCategory === cat
                    ? 'bg-[#fd7e14] text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-[#1e2c3f]'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          {/* User Status Filter */}
          <div className="flex items-center space-x-1 border-l border-[#25354b] pl-2">
            {(['all', 'admin', 'active'] as const).map((filter) => (
              <button
                key={filter}
                onClick={() => setUserFilter(filter)}
                className={`px-2 py-1 rounded-md text-[11px] font-medium capitalize transition-colors ${
                  userFilter === filter
                    ? 'bg-[#1e2c3f] text-[#fd7e14] font-semibold border border-[#2c3f58]'
                    : 'text-slate-400 hover:text-slate-300'
                }`}
              >
                {filter}
              </button>
            ))}
          </div>
        </div>

      </div>

      {/* Staged Changes Notification Bar */}
      {stagedMode && (
        <div className="bg-[#16202e] border-b border-orange-500/30 px-5 py-2 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <span className="h-2 w-2 rounded-full bg-[#fd7e14] animate-ping" />
            <span className="text-xs font-semibold text-slate-200">
              Staged Review: <span className="text-[#fd7e14] font-bold">{stagedChanges.length}</span> change(s) queued.
            </span>
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={onDiscardStagedChanges}
              disabled={loading || stagedChanges.length === 0}
              className="px-2.5 py-1 text-xs text-slate-400 hover:text-rose-400 disabled:opacity-40 transition-colors"
            >
              Discard
            </button>
            <button
              onClick={onApplyStagedChanges}
              disabled={loading || stagedChanges.length === 0}
              className="bg-[#fd7e14] hover:bg-[#ea6c0a] disabled:opacity-40 text-white text-xs font-semibold px-3 py-1 rounded-md shadow transition-colors flex items-center space-x-1"
            >
              <Check className="h-3 w-3" />
              <span>Apply Changes</span>
            </button>
          </div>
        </div>
      )}

      {/* Access Matrix Scrollable Table */}
      <div className="overflow-x-auto flex-1">
        <table className="w-full border-collapse text-left">
          
          {/* Table Header: Applications */}
          <thead>
            <tr className="border-b border-[#25354b] bg-[#16202e]">
              
              {/* User Identity Column Header */}
              <th className="sticky left-0 z-20 bg-[#16202e] px-4 py-3.5 text-xs font-semibold text-slate-300 min-w-[220px] border-r border-[#25354b]">
                <div className="flex items-center justify-between">
                  <span>Users ({filteredUsers.length})</span>
                  <span className="text-[10px] text-slate-500 font-mono">Role Status</span>
                </div>
              </th>

              {/* Application Columns */}
              {filteredApps.map((app) => (
                <th
                  key={app.pk}
                  className="px-3 py-3 text-center min-w-[125px] border-r border-[#25354b]/70 align-top"
                >
                  <div className="flex flex-col items-center justify-center space-y-1">
                    {app.meta_icon ? (
                      <img
                        src={app.meta_icon}
                        alt={app.name}
                        className="h-6 w-6 rounded object-contain bg-[#0b0f17] p-0.5 border border-[#25354b]"
                      />
                    ) : (
                      <div className="h-6 w-6 rounded bg-[#1e2c3f] text-[#fd7e14] flex items-center justify-center font-bold text-[10px] border border-[#2c3f58]">
                        {app.name.substring(0, 2).toUpperCase()}
                      </div>
                    )}
                    <div 
                      className="text-xs font-semibold text-slate-200 truncate max-w-[115px] flex items-center justify-center gap-1"
                      title={app.name}
                    >
                      <span className="truncate">{app.name}</span>
                      {app.has_granular_admin_group && (
                        <span title="Configured with dedicated App Admin group">
                          <Crown className="h-3 w-3 text-[#fd7e14] shrink-0" />
                        </span>
                      )}
                    </div>
                  </div>
                </th>
              ))}

            </tr>
          </thead>

          {/* Table Body: User Rows */}
          <tbody className="divide-y divide-[#25354b]/50">
            {filteredUsers.length === 0 ? (
              <tr>
                <td
                  colSpan={filteredApps.length + 1}
                  className="px-6 py-14 text-center text-slate-400 text-xs bg-[#0b0f17]/40"
                >
                  No users matched your filter criteria.
                </td>
              </tr>
            ) : (
              filteredUsers.map((user) => {
                const uPkStr = String(user.pk);
                const userPermissions = data.permissions[uPkStr] || {};
                const userAdminPermissions = data.admin_permissions?.[uPkStr] || {};
                const userInheritedAccess = data.inherited_access?.[uPkStr] || {};

                return (
                  <tr
                    key={user.pk}
                    className="hover:bg-[#16202e]/40 transition-colors group"
                  >
                    
                    {/* User Identity Column (Sticky Left) */}
                    <td className="sticky left-0 z-10 bg-[#111827] group-hover:bg-[#131b27] px-4 py-2.5 border-r border-[#25354b] transition-colors">
                      <div className="flex items-center space-x-2.5">
                        <div className="relative shrink-0">
                          {user.avatar ? (
                            <img
                              src={user.avatar}
                              alt={user.name}
                              className="h-7 w-7 rounded-full border border-[#25354b] object-cover"
                            />
                          ) : (
                            <div className="h-7 w-7 rounded-full bg-[#1e2c3f] text-slate-200 font-bold text-[10px] flex items-center justify-center border border-[#2c3f58]">
                              {user.name.substring(0, 2).toUpperCase()}
                            </div>
                          )}
                          <span
                            className={`absolute bottom-0 right-0 h-2 w-2 rounded-full border-2 border-[#111827] ${
                              user.is_active ? 'bg-emerald-400' : 'bg-slate-500'
                            }`}
                          />
                        </div>

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center space-x-1.5">
                            <span className="text-xs font-semibold text-slate-200 truncate max-w-[125px]">
                              {user.name}
                            </span>
                            {user.is_superuser && (
                              <span
                                title="Authentik Superuser (Unrestricted Access)"
                                className="px-1.5 py-0.2 rounded text-[9px] bg-orange-500/15 text-[#fd7e14] border border-orange-500/30 font-semibold"
                              >
                                Superuser
                              </span>
                            )}
                          </div>
                          <div className="text-[10px] text-slate-500 truncate max-w-[140px]">
                            @{user.username}
                          </div>
                        </div>

                        {/* Account Suspend / Activate Button */}
                        {!user.is_superuser && (
                          <button
                            onClick={() => onToggleUserActive(user.pk)}
                            title={user.is_active ? 'Suspend Account' : 'Activate Account'}
                            className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-[#1e2c3f] text-slate-400 hover:text-slate-200 transition-opacity"
                          >
                            {user.is_active ? (
                              <UserCheck className="h-3.5 w-3.5 text-emerald-400" />
                            ) : (
                              <UserX className="h-3.5 w-3.5 text-rose-400" />
                            )}
                          </button>
                        )}

                      </div>
                    </td>

                    {/* Cell for each Application */}
                    {filteredApps.map((app) => {
                      // Determine current permissions
                      const isSuperuser = user.is_superuser;
                      const hasAdmin = isSuperuser ? true : !!userAdminPermissions[app.pk];
                      const hasAccess = isSuperuser ? true : !!userPermissions[app.pk];
                      const inheritedGroups = userInheritedAccess[app.pk] || [];
                      const isInherited = !isSuperuser && inheritedGroups.length > 0;

                      // Check direct group membership
                      const userGroupPk = app.granular_user_group_pk || app.bound_group_pk;
                      const adminGroupPk = app.granular_admin_group_pk;
                      const isDirectMember = Boolean(userGroupPk && user.groups.includes(userGroupPk));
                      const isDirectAdmin = Boolean(adminGroupPk && user.groups.includes(adminGroupPk));

                      // Current effective role
                      let currentRole: 'none' | 'member' | 'admin' | 'inherited' = 'none';
                      if (hasAdmin || isDirectAdmin) {
                        currentRole = 'admin';
                      } else if (isDirectMember) {
                        currentRole = 'member';
                      } else if (isInherited) {
                        currentRole = 'inherited';
                      } else if (hasAccess) {
                        currentRole = 'member';
                      }

                      // Check staged changes
                      const appStaged = stagedMap.get(`${user.pk}-${app.pk}`) || [];
                      const isStagedPending = appStaged.length > 0;
                      let stagedPreviewRole: 'none' | 'member' | 'admin' | null = null;
                      if (isStagedPending) {
                        const adminStaged = appStaged.find(s => s.group_pk === adminGroupPk);
                        const userStaged = appStaged.find(s => s.group_pk === userGroupPk);
                        if (adminStaged?.grant) {
                          stagedPreviewRole = 'admin';
                        } else if (userStaged?.grant) {
                          stagedPreviewRole = 'member';
                        } else if (userStaged?.grant === false && adminStaged?.grant === false) {
                          stagedPreviewRole = 'none';
                        } else if (userStaged?.grant === false) {
                          stagedPreviewRole = 'none';
                        }
                      }

                      const effectiveRole = stagedPreviewRole || currentRole;

                      return (
                        <td
                          key={app.pk}
                          className="px-2 py-2 text-center border-r border-[#25354b]/50 relative"
                        >
                          <div className="flex items-center justify-center">
                            
                            {isSuperuser ? (
                              <div
                                title="Superuser has unrestricted access to all applications"
                                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-semibold bg-orange-500/10 text-[#fd7e14] border border-orange-500/20 cursor-default select-none"
                              >
                                <Lock className="h-3 w-3 text-[#fd7e14]" />
                                <span>Superuser</span>
                              </div>
                            ) : !app.bound_group_pk && !app.has_granular_user_group ? (
                              <button
                                onClick={() => onProvisionApp(app.pk)}
                                title="Application is unrestricted or unconfigured. Click to secure."
                                className="px-2.5 py-1 rounded-md bg-[#1e2c3f] hover:bg-[#25354b] text-[11px] font-medium text-amber-400 border border-amber-500/30 transition-colors"
                              >
                                + Setup
                              </button>
                            ) : (
                              /* Clean Role Badge Pill */
                              <button
                                onClick={(e) => handleCellClick(e, user, app, currentRole, inheritedGroups)}
                                disabled={loading}
                                className={`group/pill relative inline-flex items-center justify-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold transition-all select-none ${
                                  isStagedPending
                                    ? stagedPreviewRole === 'admin'
                                      ? 'bg-orange-500/20 text-[#fd7e14] border-2 border-orange-400 shadow-md animate-pulse'
                                      : stagedPreviewRole === 'member'
                                      ? 'bg-emerald-500/20 text-emerald-300 border-2 border-emerald-400 shadow-md animate-pulse'
                                      : 'bg-rose-500/20 text-rose-300 border-2 border-rose-400 shadow-md animate-pulse'
                                    : effectiveRole === 'admin'
                                    ? 'bg-orange-500/15 text-[#fd7e14] border border-orange-500/30 hover:bg-orange-500/25 shadow-sm'
                                    : effectiveRole === 'member'
                                    ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25 shadow-sm'
                                    : effectiveRole === 'inherited'
                                    ? 'bg-[#0284c7]/15 text-[#38bdf8] border border-[#0284c7]/30 hover:bg-[#0284c7]/25 shadow-sm'
                                    : 'text-slate-500 hover:text-slate-200 hover:bg-[#1e2c3f] border border-transparent hover:border-[#2c3f58]'
                                }`}
                                title={
                                  isStagedPending
                                    ? `Staged change pending: ${stagedPreviewRole?.toUpperCase()}`
                                    : effectiveRole === 'admin'
                                    ? `Administrator (${app.name}). Click to change role.`
                                    : effectiveRole === 'member'
                                    ? `Member (${app.name}). Click to change role.`
                                    : effectiveRole === 'inherited'
                                    ? `Access inherited via ${inheritedGroups.join(', ')}. Click to configure individual role.`
                                    : `No access to ${app.name}. Click to assign role.`
                                }
                              >
                                {effectiveRole === 'admin' ? (
                                  <>
                                    <Crown className="h-3.5 w-3.5 text-[#fd7e14] shrink-0" />
                                    <span>Admin</span>
                                  </>
                                ) : effectiveRole === 'member' ? (
                                  <>
                                    <Check className="h-3.5 w-3.5 text-emerald-400 stroke-[2.5] shrink-0" />
                                    <span>Member</span>
                                  </>
                                ) : effectiveRole === 'inherited' ? (
                                  <>
                                    <Flag className="h-3 w-3 text-[#38bdf8] shrink-0" />
                                    <span>Inherited</span>
                                  </>
                                ) : (
                                  <span className="text-slate-500 group-hover/pill:text-slate-300 text-xs px-1">
                                    —
                                  </span>
                                )}

                                {/* Subtle corner indicator for inherited access if also an individual member */}
                                {isInherited && effectiveRole !== 'inherited' && !isStagedPending && (
                                  <span
                                    className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-[#0284c7] border border-[#111827]"
                                    title={`Also inherited from: ${inheritedGroups.join(', ')}`}
                                  />
                                )}
                              </button>
                            )}

                          </div>
                        </td>
                      );
                    })}

                  </tr>
                );
              })
            )}
          </tbody>

        </table>
      </div>

      {/* Clean Table Footer: Legend */}
      <div className="px-4 py-3 border-t border-[#25354b] bg-[#16202e] flex flex-wrap items-center justify-between gap-3 text-[11px] text-slate-400">
        <div className="flex flex-wrap items-center gap-5 sm:gap-6">
          <div className="flex items-center space-x-2">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
              <Check className="h-3 w-3 text-emerald-400 stroke-[2.5]" />
              <span>Member</span>
            </span>
            <span>Standard app access</span>
          </div>

          <div className="flex items-center space-x-2">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-orange-500/15 text-[#fd7e14] border border-orange-500/30">
              <Crown className="h-3 w-3 text-[#fd7e14]" />
              <span>Admin</span>
            </span>
            <span>Dedicated app admin group</span>
          </div>

          <div className="flex items-center space-x-2">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-[#0284c7]/15 text-[#38bdf8] border border-[#0284c7]/30">
              <Flag className="h-3 w-3 text-[#38bdf8]" />
              <span>Inherited</span>
            </span>
            <span>Granted via global group (e.g. 5AMT Home)</span>
          </div>

          <div className="flex items-center space-x-2">
            <span className="inline-flex items-center justify-center px-2 py-0.5 rounded text-xs text-slate-400 border border-[#25354b] bg-[#0b0f17]">
              —
            </span>
            <span>No access</span>
          </div>
        </div>

        <div className="text-slate-400 flex items-center gap-1.5 font-medium">
          <Sparkles className="h-3.5 w-3.5 text-[#fd7e14]" />
          <span>Click any role badge to change access level</span>
        </div>
      </div>

      {/* Floating Role Selector Popover (Anchored at clicked cell) */}
      {popover && (
        <div
          ref={popoverRef}
          style={{
            position: 'fixed',
            top: Math.min(window.innerHeight - 280, Math.max(10, popover.rect.bottom + 6)),
            left: Math.min(window.innerWidth - 290, Math.max(10, popover.rect.left - 40)),
            zIndex: 100,
          }}
          className="w-72 bg-[#16202e] border border-[#2c3f58] rounded-xl shadow-2xl p-3.5 text-xs animate-in fade-in zoom-in-95 duration-100"
        >
          {/* Popover Header */}
          <div className="flex items-start justify-between pb-2.5 mb-2.5 border-b border-[#25354b]">
            <div>
              <div className="flex items-center space-x-1.5 font-bold text-white text-sm">
                <span>{popover.app.name}</span>
              </div>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Role for <strong className="text-slate-200">{popover.user.name}</strong>
              </p>
            </div>
            <button
              onClick={() => setPopover(null)}
              className="p-1 rounded-md text-slate-400 hover:text-white hover:bg-[#1e2c3f] transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Role Options */}
          <div className="space-y-1.5">
            
            {/* 1. None / No Access */}
            <button
              onClick={() => handleSelectRole('none')}
              className={`w-full flex items-center justify-between p-2 rounded-lg text-left transition-all ${
                popover.currentRole === 'none'
                  ? 'bg-[#1e2c3f] border border-[#2c3f58] text-white'
                  : 'hover:bg-[#1e2c3f]/60 text-slate-300'
              }`}
            >
              <div className="flex items-center space-x-2.5">
                <XCircle className="h-4 w-4 text-slate-400" />
                <div>
                  <div className="font-semibold text-xs">No Access</div>
                  <div className="text-[10px] text-slate-400">Revoke individual app access</div>
                </div>
              </div>
              {popover.currentRole === 'none' && (
                <CheckCircle2 className="h-4 w-4 text-slate-300 shrink-0" />
              )}
            </button>

            {/* 2. Member */}
            <button
              onClick={() => handleSelectRole('member')}
              className={`w-full flex items-center justify-between p-2 rounded-lg text-left transition-all ${
                popover.currentRole === 'member'
                  ? 'bg-emerald-500/15 border border-emerald-500/30 text-emerald-200'
                  : 'hover:bg-[#1e2c3f]/60 text-slate-300'
              }`}
            >
              <div className="flex items-center space-x-2.5">
                <Check className="h-4 w-4 text-emerald-400 stroke-[2.5]" />
                <div>
                  <div className="font-semibold text-xs text-white">Member</div>
                  <div className="text-[10px] text-slate-400">
                    {popover.app.granular_user_group_name || 'Standard user group'}
                  </div>
                </div>
              </div>
              {popover.currentRole === 'member' && (
                <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
              )}
            </button>

            {/* 3. Administrator */}
            <button
              onClick={() => handleSelectRole('admin')}
              className={`w-full flex items-center justify-between p-2 rounded-lg text-left transition-all ${
                popover.currentRole === 'admin'
                  ? 'bg-orange-500/15 border border-orange-500/30 text-orange-200'
                  : 'hover:bg-[#1e2c3f]/60 text-slate-300'
              }`}
            >
              <div className="flex items-center space-x-2.5">
                <Crown className="h-4 w-4 text-[#fd7e14]" />
                <div>
                  <div className="font-semibold text-xs text-white">Administrator</div>
                  <div className="text-[10px] text-slate-400">
                    {popover.app.granular_admin_group_name || (popover.app.has_granular_admin_group ? 'App Admin group' : 'Auto-provisions Admin group')}
                  </div>
                </div>
              </div>
              {popover.currentRole === 'admin' && (
                <CheckCircle2 className="h-4 w-4 text-[#fd7e14] shrink-0" />
              )}
            </button>

          </div>

          {/* Inherited Access Info (if applicable) */}
          {popover.inheritedGroups.length > 0 && (
            <div className="mt-3 pt-2.5 border-t border-[#25354b] text-[10px] text-sky-300/90 bg-[#0284c7]/10 p-2 rounded-md border border-[#0284c7]/20 flex items-start gap-1.5">
              <Flag className="h-3.5 w-3.5 text-[#38bdf8] shrink-0 mt-0.5" />
              <div>
                <span>User also has base access inherited from: </span>
                <span className="font-semibold text-white">{popover.inheritedGroups.join(', ')}</span>
              </div>
            </div>
          )}

        </div>
      )}

    </div>
  );
};
