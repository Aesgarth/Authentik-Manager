import React, { useState, useMemo } from 'react';
import { 
  Search, 
  Shield, 
  Check, 
  X, 
  Lock, 
  UserCheck, 
  UserX,
  Plus,
  Minus
} from 'lucide-react';
import { AccessMatrixData, User, Application, StagedChange } from '../types';

interface AccessMatrixProps {
  data: AccessMatrixData;
  stagedMode: boolean;
  stagedChanges: StagedChange[];
  onToggleCell: (user: User, app: Application, currentAccess: boolean) => void;
  onApplyStagedChanges: () => void;
  onDiscardStagedChanges: () => void;
  onToggleUserActive: (user_pk: number) => void;
  onProvisionApp: (app_pk: string) => void;
  loading: boolean;
}

export const AccessMatrix: React.FC<AccessMatrixProps> = ({
  data,
  stagedMode,
  stagedChanges,
  onToggleCell,
  onApplyStagedChanges,
  onDiscardStagedChanges,
  onToggleUserActive,
  onProvisionApp,
  loading,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [userFilter, setUserFilter] = useState<'all' | 'admin' | 'active' | 'inactive'>('all');

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

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl shadow-xl overflow-hidden flex flex-col">
      
      {/* Matrix Controls / Toolbar */}
      <div className="p-4 border-b border-slate-800 bg-slate-900/50 flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-4">
        
        {/* Search */}
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search users by name, username, or email..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-slate-950/80 border border-slate-800 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
          />
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2">
          
          {/* Category Filter */}
          <div className="flex items-center space-x-1 overflow-x-auto py-1">
            <button
              onClick={() => setSelectedCategory('all')}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                selectedCategory === 'all'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'bg-slate-950/60 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
            >
              All Categories ({data.apps.length})
            </button>
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-3 py-1 rounded-lg text-xs font-medium whitespace-nowrap transition-colors ${
                  selectedCategory === cat
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'bg-slate-950/60 text-slate-400 hover:text-slate-200 border border-slate-800'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          {/* User Type Filter */}
          <select
            value={userFilter}
            onChange={(e) => setUserFilter(e.target.value as any)}
            className="bg-slate-950/80 border border-slate-800 text-slate-300 text-xs rounded-xl px-3 py-1.5 focus:outline-none focus:border-indigo-500"
          >
            <option value="all">All Users ({data.users.length})</option>
            <option value="admin">Superusers Only</option>
            <option value="active">Active Accounts</option>
            <option value="inactive">Suspended Accounts</option>
          </select>

        </div>

      </div>

      {/* Interactive Matrix Table */}
      <div className="overflow-x-auto relative flex-1">
        <table className="w-full text-left border-collapse">
          
          {/* Header Row: Applications */}
          <thead>
            <tr className="bg-slate-950/90 border-b border-slate-800">
              
              {/* Sticky User Column Header */}
              <th className="sticky left-0 z-20 bg-slate-950/95 backdrop-blur px-4 py-3.5 text-xs font-semibold text-slate-300 border-r border-slate-800 min-w-[260px]">
                <div className="flex items-center justify-between">
                  <span>User / Identity</span>
                  <span className="text-[10px] font-normal text-slate-400">
                    {filteredUsers.length} shown
                  </span>
                </div>
              </th>

              {/* Application Columns */}
              {filteredApps.map((app) => (
                <th
                  key={app.pk}
                  className="px-4 py-3 text-center min-w-[150px] border-r border-slate-800/60 bg-slate-950/80"
                >
                  <div className="flex flex-col items-center justify-center space-y-1">
                    <div className="relative">
                      {app.meta_icon ? (
                        <img
                          src={app.meta_icon}
                          alt={app.name}
                          className="h-7 w-7 rounded-lg object-contain bg-slate-900 p-1 border border-slate-800"
                          onError={(e) => {
                            (e.target as HTMLElement).style.display = 'none';
                          }}
                        />
                      ) : (
                        <div className="h-7 w-7 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 flex items-center justify-center font-bold text-xs">
                          {app.name.substring(0, 2).toUpperCase()}
                        </div>
                      )}
                      {!app.is_protected && (
                        <span
                          title="Unprotected: Accessible to all users in Authentik! Click to secure."
                          onClick={() => onProvisionApp(app.pk)}
                          className="absolute -top-1 -right-1 h-3.5 w-3.5 rounded-full bg-rose-500 text-white text-[9px] font-bold flex items-center justify-center shadow cursor-pointer hover:scale-110 transition-transform"
                        >
                          !
                        </span>
                      )}
                    </div>
                    <span className="text-xs font-semibold text-slate-200 truncate max-w-[130px]" title={app.name}>
                      {app.name}
                    </span>
                    <span
                      className={`text-[10px] px-1.5 py-0.2 rounded-full border ${
                        app.is_protected
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                          : 'bg-rose-500/10 text-rose-400 border-rose-500/20 cursor-pointer hover:bg-rose-500/20'
                      }`}
                      onClick={() => !app.is_protected && onProvisionApp(app.pk)}
                      title={app.bound_group_name ? `Bound Group: ${app.bound_group_name}` : 'Click to provision group'}
                    >
                      {app.is_protected ? 'Secured' : 'Open (Click to Lock)'}
                    </span>
                  </div>
                </th>
              ))}

            </tr>
          </thead>

          {/* Table Body: User Rows */}
          <tbody className="divide-y divide-slate-800/80">
            {filteredUsers.length === 0 ? (
              <tr>
                <td
                  colSpan={filteredApps.length + 1}
                  className="px-6 py-12 text-center text-slate-400 text-sm"
                >
                  No users matched your search criteria.
                </td>
              </tr>
            ) : (
              filteredUsers.map((user) => {
                const uPkStr = String(user.pk);
                const userPermissions = data.permissions[uPkStr] || {};

                return (
                  <tr
                    key={user.pk}
                    className="hover:bg-slate-800/30 transition-colors group"
                  >
                    
                    {/* User Identity Column (Sticky) */}
                    <td className="sticky left-0 z-10 bg-slate-900/95 backdrop-blur px-4 py-3 border-r border-slate-800">
                      <div className="flex items-center space-x-3">
                        <div className="relative">
                          {user.avatar ? (
                            <img
                              src={user.avatar}
                              alt={user.name}
                              className="h-8 w-8 rounded-full border border-slate-700 object-cover"
                            />
                          ) : (
                            <div className="h-8 w-8 rounded-full bg-slate-800 text-slate-300 font-bold text-xs flex items-center justify-center border border-slate-700">
                              {user.name.substring(0, 2).toUpperCase()}
                            </div>
                          )}
                          <span
                            className={`absolute bottom-0 right-0 h-2 w-2 rounded-full border border-slate-900 ${
                              user.is_active ? 'bg-emerald-500' : 'bg-slate-500'
                            }`}
                          />
                        </div>

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center space-x-1.5">
                            <span className="text-xs font-semibold text-slate-200 truncate">
                              {user.name}
                            </span>
                            {user.is_superuser && (
                              <span
                                title="Superuser (Bypasses all policy bindings)"
                                className="px-1 py-0.2 rounded text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/30 flex items-center gap-0.5"
                              >
                                <Shield className="h-2.5 w-2.5" />
                                Admin
                              </span>
                            )}
                          </div>
                          <div className="text-[11px] text-slate-400 truncate">
                            @{user.username} {user.email && `• ${user.email}`}
                          </div>
                        </div>

                        {/* Suspend / Activate User Button */}
                        {!user.is_superuser && (
                          <button
                            onClick={() => onToggleUserActive(user.pk)}
                            title={user.is_active ? 'Suspend Account' : 'Activate Account'}
                            className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-opacity"
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
                      const hasCurrentAccess = user.is_superuser ? true : !!userPermissions[app.pk];
                      const stagedChange = stagedMap.get(`${user.pk}-${app.pk}`);
                      
                      // Calculate effective display state
                      const effectiveAccess = stagedChange ? stagedChange.grant : hasCurrentAccess;
                      const isStagedPending = Boolean(stagedChange);

                      return (
                        <td
                          key={app.pk}
                          className="px-4 py-3 text-center border-r border-slate-800/40 relative"
                        >
                          <div className="flex items-center justify-center">
                            
                            {user.is_superuser ? (
                              <div
                                title="Superuser has inherent full access to all services"
                                className="h-8 w-8 rounded-lg bg-amber-500/10 text-amber-400/80 border border-amber-500/20 flex items-center justify-center cursor-default"
                              >
                                <Lock className="h-3.5 w-3.5 text-amber-400" />
                              </div>
                            ) : !app.bound_group_pk ? (
                              <button
                                onClick={() => onProvisionApp(app.pk)}
                                title="No dedicated group provisioned yet. Click to secure application."
                                className="px-2 py-1 rounded bg-slate-800/60 hover:bg-slate-700 text-[10px] text-amber-400 border border-amber-500/30 transition-colors"
                              >
                                Secure App
                              </button>
                            ) : (
                              <button
                                onClick={() => onToggleCell(user, app, hasCurrentAccess)}
                                disabled={loading}
                                className={`relative h-8 w-8 rounded-lg flex items-center justify-center transition-all ${
                                  isStagedPending
                                    ? stagedChange?.grant
                                      ? 'bg-emerald-500/20 text-emerald-300 border-2 border-emerald-400 shadow-md shadow-emerald-500/20 scale-105'
                                      : 'bg-rose-500/20 text-rose-300 border-2 border-rose-400 shadow-md shadow-rose-500/20 scale-105'
                                    : effectiveAccess
                                    ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/25'
                                    : 'bg-slate-950/70 text-slate-600 border border-slate-800 hover:text-slate-400 hover:border-slate-700'
                                }`}
                                title={
                                  isStagedPending
                                    ? `Staged: ${stagedChange?.grant ? 'Grant' : 'Revoke'} access to ${app.name}`
                                    : effectiveAccess
                                    ? `Granted. Click to revoke access to ${app.name}`
                                    : `Denied. Click to grant access to ${app.name}`
                                }
                              >
                                {isStagedPending ? (
                                  stagedChange?.grant ? (
                                    <Plus className="h-4 w-4 text-emerald-400 stroke-[3]" />
                                  ) : (
                                    <Minus className="h-4 w-4 text-rose-400 stroke-[3]" />
                                  )
                                ) : effectiveAccess ? (
                                  <Check className="h-4 w-4 text-emerald-400 stroke-[2.5]" />
                                ) : (
                                  <X className="h-3.5 w-3.5 text-slate-600 group-hover:text-slate-400" />
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

      {/* Staged Changes Confirmation Bar */}
      {stagedMode && stagedChanges.length > 0 && (
        <div className="bg-slate-950 border-t border-indigo-500/40 p-4 sticky bottom-0 z-30 shadow-2xl flex flex-col sm:flex-row items-center justify-between gap-3 animate-in fade-in slide-in-from-bottom-2">
          <div className="flex items-center space-x-3">
            <div className="h-8 w-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center font-bold text-xs shadow-md">
              {stagedChanges.length}
            </div>
            <div>
              <p className="text-xs font-semibold text-slate-100">
                You have {stagedChanges.length} staged permission change{stagedChanges.length > 1 ? 's' : ''} ready to apply.
              </p>
              <p className="text-[11px] text-slate-400">
                Changes will be committed to Authentik policy groups once confirmed.
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2 self-end sm:self-center">
            <button
              onClick={onDiscardStagedChanges}
              disabled={loading}
              className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
            >
              Discard All
            </button>
            <button
              onClick={onApplyStagedChanges}
              disabled={loading}
              className="flex items-center space-x-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold px-4 py-2 rounded-lg shadow-lg shadow-indigo-600/30 transition-all"
            >
              <Check className="h-3.5 w-3.5" />
              <span>{loading ? 'Applying Changes...' : `Commit ${stagedChanges.length} Changes`}</span>
            </button>
          </div>
        </div>
      )}

    </div>
  );
};
