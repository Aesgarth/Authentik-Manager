import React, { useState, useMemo } from 'react';
import { 
  Search, 
  Check, 
  Lock, 
  UserCheck, 
  UserX,
  Plus, 
  Minus,
  Crown,
  Sparkles
} from 'lucide-react';
import { AccessMatrixData, User, Application, StagedChange } from '../types';

interface AccessMatrixProps {
  data: AccessMatrixData;
  stagedMode: boolean;
  stagedChanges: StagedChange[];
  onToggleCell: (user: User, app: Application, currentAccess: boolean) => void;
  onToggleAdminCell?: (user: User, app: Application, currentAdmin: boolean) => void;
  onApplyStagedChanges: () => void;
  onDiscardStagedChanges: () => void;
  onToggleUserActive: (user_pk: number) => void;
  onProvisionApp: (app_pk: string) => void;
  onProvisionAll?: (options?: any) => Promise<any>;
  loading: boolean;
}

export const AccessMatrix: React.FC<AccessMatrixProps> = ({
  data,
  stagedMode,
  stagedChanges,
  onToggleCell,
  onToggleAdminCell,
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

  // Fast staged change lookup: `${user_pk}-${app_pk}` -> StagedChange
  const stagedMap = useMemo(() => {
    const map = new Map<string, StagedChange>();
    stagedChanges.forEach((sc) => {
      map.set(`${sc.user_pk}-${sc.app_pk}`, sc);
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

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl shadow-xl overflow-hidden flex flex-col">
      
      {/* 1-Click Granular RBAC Setup Callout (Only appears if broad groups are in use) */}
      {appsNeedingGranular.length > 0 && onProvisionAll && (
        <div className="bg-gradient-to-r from-indigo-950/70 via-slate-900 to-slate-900 border-b border-indigo-500/30 px-5 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
          <div className="flex items-center space-x-2.5 text-slate-300">
            <div className="h-7 w-7 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center shrink-0">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <p className="font-semibold text-indigo-200">
                Granular Per-Service Groups Available
              </p>
              <p className="text-[11px] text-slate-400">
                {appsNeedingGranular.length} of your services currently share global groups. Set up individual access and admin groups with 1 click.
              </p>
            </div>
          </div>
          <button
            onClick={handleQuickProvisionAll}
            disabled={loading || provisioningAll}
            className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold px-3.5 py-1.5 rounded-xl transition-all shadow-sm flex items-center justify-center gap-1.5 shrink-0"
          >
            <Sparkles className="h-3.5 w-3.5" />
            <span>{provisioningAll ? 'Setting up...' : `Auto-Setup All (${appsNeedingGranular.length})`}</span>
          </button>
        </div>
      )}

      {/* Matrix Controls & Search Toolbar */}
      <div className="p-3.5 border-b border-slate-800/80 bg-slate-900/60 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        
        {/* Search */}
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-500" />
          <input
            type="text"
            placeholder="Search users..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-8 pr-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
          />
        </div>

        {/* Clean Filter Pills */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Category Filter */}
          <div className="flex items-center space-x-1 overflow-x-auto py-0.5">
            <button
              onClick={() => setSelectedCategory('all')}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                selectedCategory === 'all'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              All ({data.apps.length})
            </button>
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors whitespace-nowrap ${
                  selectedCategory === cat
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          {/* User Status Filter */}
          <div className="flex items-center space-x-1 border-l border-slate-800 pl-2">
            {(['all', 'admin', 'active'] as const).map((filter) => (
              <button
                key={filter}
                onClick={() => setUserFilter(filter)}
                className={`px-2 py-1 rounded-lg text-[11px] font-medium capitalize transition-colors ${
                  userFilter === filter
                    ? 'bg-slate-800 text-indigo-400 font-semibold'
                    : 'text-slate-500 hover:text-slate-300'
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
        <div className="bg-indigo-950/60 border-b border-indigo-500/30 px-5 py-2 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <span className="h-2 w-2 rounded-full bg-amber-400 animate-ping" />
            <span className="text-xs font-semibold text-indigo-200">
              Staged Review: <span className="text-amber-300 font-bold">{stagedChanges.length}</span> change(s) ready to apply.
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
              className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-xs font-semibold px-3 py-1 rounded-lg shadow transition-colors flex items-center space-x-1"
            >
              <Check className="h-3 w-3" />
              <span>Apply</span>
            </button>
          </div>
        </div>
      )}

      {/* Access Matrix Scrollable Table */}
      <div className="overflow-x-auto flex-1">
        <table className="w-full border-collapse text-left">
          
          {/* Table Header: Applications */}
          <thead>
            <tr className="border-b border-slate-800/80 bg-slate-950/70">
              
              {/* User Identity Column Header */}
              <th className="sticky left-0 z-20 bg-slate-950/95 backdrop-blur px-4 py-3 text-xs font-semibold text-slate-400 min-w-[210px] border-r border-slate-800/80">
                <span>User ({filteredUsers.length})</span>
              </th>

              {/* Application Columns */}
              {filteredApps.map((app) => (
                <th
                  key={app.pk}
                  className="px-2.5 py-2.5 text-center min-w-[110px] border-r border-slate-800/50 align-top"
                >
                  <div className="flex flex-col items-center justify-center space-y-1">
                    {app.meta_icon ? (
                      <img
                        src={app.meta_icon}
                        alt={app.name}
                        className="h-6 w-6 rounded object-contain bg-slate-900 p-0.5 border border-slate-800"
                      />
                    ) : (
                      <div className="h-6 w-6 rounded bg-indigo-500/10 text-indigo-400 flex items-center justify-center font-bold text-[10px] border border-indigo-500/20">
                        {app.name.substring(0, 2).toUpperCase()}
                      </div>
                    )}
                    <span 
                      className="text-xs font-semibold text-slate-200 truncate max-w-[105px] flex items-center justify-center gap-1"
                      title={app.name}
                    >
                      <span>{app.name}</span>
                      {app.has_granular_admin_group && (
                        <span title="Configured with dedicated App Admin group">
                          <Crown className="h-2.5 w-2.5 text-amber-400 shrink-0" />
                        </span>
                      )}
                    </span>
                  </div>
                </th>
              ))}

            </tr>
          </thead>

          {/* Table Body: User Rows */}
          <tbody className="divide-y divide-slate-800/60">
            {filteredUsers.length === 0 ? (
              <tr>
                <td
                  colSpan={filteredApps.length + 1}
                  className="px-6 py-12 text-center text-slate-500 text-xs"
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
                    className="hover:bg-slate-800/25 transition-colors group"
                  >
                    
                    {/* User Identity Column (Sticky) */}
                    <td className="sticky left-0 z-10 bg-slate-900/95 backdrop-blur px-4 py-2.5 border-r border-slate-800/80">
                      <div className="flex items-center space-x-2.5">
                        <div className="relative shrink-0">
                          {user.avatar ? (
                            <img
                              src={user.avatar}
                              alt={user.name}
                              className="h-7 w-7 rounded-full border border-slate-700 object-cover"
                            />
                          ) : (
                            <div className="h-7 w-7 rounded-full bg-slate-800 text-slate-300 font-bold text-[10px] flex items-center justify-center border border-slate-700">
                              {user.name.substring(0, 2).toUpperCase()}
                            </div>
                          )}
                          <span
                            className={`absolute bottom-0 right-0 h-1.5 w-1.5 rounded-full border border-slate-900 ${
                              user.is_active ? 'bg-emerald-500' : 'bg-slate-500'
                            }`}
                          />
                        </div>

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center space-x-1.5">
                            <span className="text-xs font-semibold text-slate-200 truncate max-w-[120px]">
                              {user.name}
                            </span>
                            {user.is_superuser && (
                              <span
                                title="Superuser (Global Access)"
                                className="px-1 py-0.2 rounded text-[9px] bg-amber-500/20 text-amber-300 border border-amber-500/30 font-medium"
                              >
                                Admin
                              </span>
                            )}
                          </div>
                          <div className="text-[10px] text-slate-500 truncate max-w-[140px]">
                            @{user.username}
                          </div>
                        </div>

                        {/* Account Suspend / Activate */}
                        {!user.is_superuser && (
                          <button
                            onClick={() => onToggleUserActive(user.pk)}
                            title={user.is_active ? 'Suspend Account' : 'Activate Account'}
                            className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-slate-800 text-slate-500 hover:text-slate-300 transition-opacity"
                          >
                            {user.is_active ? (
                              <UserCheck className="h-3 w-3 text-emerald-400" />
                            ) : (
                              <UserX className="h-3 w-3 text-rose-400" />
                            )}
                          </button>
                        )}

                      </div>
                    </td>

                    {/* Cell for each Application */}
                    {filteredApps.map((app) => {
                      const hasCurrentAccess = user.is_superuser ? true : !!userPermissions[app.pk];
                      const isCurrentAdmin = user.is_superuser ? true : !!userAdminPermissions[app.pk];
                      const inheritedGroups = userInheritedAccess[app.pk] || [];
                      const isInherited = !user.is_superuser && inheritedGroups.length > 0;

                      const stagedChange = stagedMap.get(`${user.pk}-${app.pk}`);
                      const effectiveAccess = stagedChange ? stagedChange.grant : hasCurrentAccess;
                      const isStagedPending = Boolean(stagedChange);

                      return (
                        <td
                          key={app.pk}
                          className="px-2 py-2 text-center border-r border-slate-800/40 relative"
                        >
                          <div className="flex items-center justify-center relative group/cell">
                            
                            {user.is_superuser ? (
                              <div
                                title="Superuser has inherent full access to all services"
                                className="h-7 w-7 rounded-lg bg-amber-500/10 text-amber-400/80 border border-amber-500/20 flex items-center justify-center cursor-default"
                              >
                                <Lock className="h-3 w-3 text-amber-400" />
                              </div>
                            ) : !app.bound_group_pk && !app.has_granular_user_group ? (
                              <button
                                onClick={() => onProvisionApp(app.pk)}
                                title="No group bound yet. Click to secure application."
                                className="px-2 py-0.5 rounded bg-slate-800/60 hover:bg-slate-700 text-[10px] text-amber-400 border border-amber-500/30 transition-colors"
                              >
                                Setup
                              </button>
                            ) : (
                              <div className="relative">
                                {/* Single Clean Access Button */}
                                <button
                                  onClick={() => onToggleCell(user, app, hasCurrentAccess)}
                                  disabled={loading}
                                  className={`relative h-7 w-7 rounded-lg flex items-center justify-center transition-all ${
                                    isStagedPending
                                      ? stagedChange?.grant
                                        ? 'bg-emerald-500/20 text-emerald-300 border-2 border-emerald-400 shadow-sm scale-105'
                                        : 'bg-rose-500/20 text-rose-300 border-2 border-rose-400 shadow-sm scale-105'
                                      : isCurrentAdmin
                                      ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm'
                                      : effectiveAccess
                                      ? isInherited
                                        ? 'bg-sky-500/15 text-sky-400 border border-sky-500/30 hover:bg-sky-500/25'
                                        : 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/25'
                                      : 'bg-slate-950/40 text-slate-600 border border-slate-800/70 hover:text-slate-300 hover:border-slate-700 hover:bg-slate-800/40'
                                  }`}
                                  title={
                                    isStagedPending
                                      ? `Staged: ${stagedChange?.grant ? 'Grant' : 'Revoke'} access to ${app.name}`
                                      : isCurrentAdmin
                                      ? `App Administrator (${app.name}). Click to toggle access.`
                                      : isInherited
                                      ? `Granted via broad group '${inheritedGroups.join(', ')}'. Click to toggle dedicated membership.`
                                      : effectiveAccess
                                      ? `Member access active. Click to revoke.`
                                      : `No access. Click to grant.`
                                  }
                                >
                                  {isStagedPending ? (
                                    stagedChange?.grant ? (
                                      <Plus className="h-3.5 w-3.5 text-emerald-400 stroke-[3]" />
                                    ) : (
                                      <Minus className="h-3.5 w-3.5 text-rose-400 stroke-[3]" />
                                    )
                                  ) : isCurrentAdmin ? (
                                    <Crown className="h-3.5 w-3.5 text-amber-300" />
                                  ) : effectiveAccess ? (
                                    <Check className={`h-3.5 w-3.5 stroke-[2.5] ${isInherited ? 'text-sky-400' : 'text-emerald-400'}`} />
                                  ) : (
                                    <span className="text-slate-600 group-hover/cell:text-slate-400 text-xs select-none">—</span>
                                  )}

                                  {/* Small subtle corner dot for inherited access */}
                                  {isInherited && !isCurrentAdmin && !isStagedPending && (
                                    <span 
                                      className="absolute -top-0.5 -right-0.5 h-1.5 w-1.5 rounded-full bg-sky-400 border border-slate-900" 
                                      title={`Inherited from: ${inheritedGroups.join(', ')}`}
                                    />
                                  )}
                                </button>

                                {/* Hoverable Quick Crown Toggle for Admin Role (only if app has admin group) */}
                                {app.granular_admin_group_pk && onToggleAdminCell && !user.is_superuser && (
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      onToggleAdminCell(user, app, isCurrentAdmin);
                                    }}
                                    disabled={loading}
                                    title={isCurrentAdmin ? 'Revoke App Admin role' : 'Grant App Admin role'}
                                    className={`absolute -top-1.5 -right-1.5 p-0.5 rounded-full border shadow-sm transition-all ${
                                      isCurrentAdmin
                                        ? 'bg-amber-500 text-slate-950 border-amber-300 opacity-100 scale-100'
                                        : 'bg-slate-800 text-slate-400 border-slate-700 opacity-0 group-hover/cell:opacity-100 hover:text-amber-300 hover:border-amber-400 hover:scale-110'
                                    }`}
                                  >
                                    <Crown className="h-2.5 w-2.5" />
                                  </button>
                                )}
                              </div>
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
      <div className="px-4 py-2.5 border-t border-slate-800/80 bg-slate-950/80 flex flex-wrap items-center justify-between gap-3 text-[11px] text-slate-400">
        <div className="flex flex-wrap items-center gap-4 sm:gap-6">
          <div className="flex items-center space-x-1.5">
            <span className="h-3.5 w-3.5 rounded bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
              <Check className="h-2.5 w-2.5 stroke-[3]" />
            </span>
            <span>Member Access</span>
          </div>

          <div className="flex items-center space-x-1.5">
            <span className="h-3.5 w-3.5 rounded bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-300">
              <Crown className="h-2.5 w-2.5" />
            </span>
            <span>App Admin Role</span>
          </div>

          <div className="flex items-center space-x-1.5">
            <span className="h-3.5 w-3.5 rounded bg-sky-500/15 border border-sky-500/30 flex items-center justify-center text-sky-400 relative">
              <Check className="h-2.5 w-2.5 stroke-[3]" />
              <span className="absolute -top-0.5 -right-0.5 h-1 w-1 rounded-full bg-sky-400" />
            </span>
            <span>Inherited Access (e.g. 5AMT Home)</span>
          </div>

          <div className="flex items-center space-x-1.5">
            <span className="h-3.5 w-3.5 rounded bg-slate-950 border border-slate-800 flex items-center justify-center text-slate-600 text-xs">
              —
            </span>
            <span>No Access</span>
          </div>
        </div>

        <div className="text-slate-500">
          Click cell to toggle access • Hover to toggle admin role
        </div>
      </div>

    </div>
  );
};
