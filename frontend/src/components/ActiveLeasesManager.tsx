import React, { useState, useMemo, useEffect } from 'react';
import { 
  Clock, 
  Search, 
  Plus, 
  RefreshCw, 
  AlertTriangle, 
  X, 
  Trash2, 
  User as UserIcon, 
  Server, 
  Crown, 
  ShieldCheck, 
  Timer
} from 'lucide-react';
import { ExpiringGrant, User, Application } from '../types';

interface ActiveLeasesManagerProps {
  leases: ExpiringGrant[];
  users: User[];
  apps: Application[];
  onRefresh: () => void;
  onExtendLease: (params: { user_pk: number; app_pk: string; group_pk: string; additional_hours: number }) => Promise<void>;
  onRevokeLease: (user_pk: number, app_pk: string, group_pk: string) => Promise<void>;
  onCreateLease: (params: {
    user_pk: number;
    user_name: string;
    app_pk: string;
    app_name: string;
    group_pk: string;
    role: 'member' | 'admin';
    duration_hours?: number;
    expires_at?: string;
  }) => Promise<void>;
  loading: boolean;
}

export const ActiveLeasesManager: React.FC<ActiveLeasesManagerProps> = ({
  leases,
  users,
  apps,
  onRefresh,
  onExtendLease,
  onRevokeLease,
  onCreateLease,
  loading,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState<'all' | 'member' | 'admin'>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | 'critical' | 'soon' | 'normal'>('all');
  
  // Create Modal State
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [selectedUserPk, setSelectedUserPk] = useState<number | ''>('');
  const [selectedAppPk, setSelectedAppPk] = useState<string>('');
  const [selectedRole, setSelectedRole] = useState<'member' | 'admin'>('member');
  const [selectedDurationHours, setSelectedDurationHours] = useState<number>(24);
  const [customHours, setCustomHours] = useState<string>('');
  const [submittingCreate, setSubmittingCreate] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Revoke confirmation state
  const [revokingLeaseKey, setRevokingLeaseKey] = useState<string | null>(null);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  // Current time state for live countdowns (updates every 10 seconds)
  const [nowMs, setNowMs] = useState<number>(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNowMs(Date.now()), 10000);
    return () => clearInterval(timer);
  }, []);

  // Compute time difference and status helpers
  const getLeaseMetrics = (lease: ExpiringGrant) => {
    const expiresMs = new Date(lease.expires_at).getTime();
    const createdMs = new Date(lease.created_at).getTime();
    const totalDuration = Math.max(1, expiresMs - createdMs);
    const remainingMs = expiresMs - nowMs;

    const isExpired = remainingMs <= 0;
    const isCritical = remainingMs > 0 && remainingMs < 2 * 60 * 60 * 1000; // < 2 hours
    const isSoon = remainingMs >= 2 * 60 * 60 * 1000 && remainingMs < 24 * 60 * 60 * 1000; // < 24 hours

    const elapsedMs = Math.max(0, nowMs - createdMs);
    const progressPercent = Math.min(100, Math.max(0, Math.round((elapsedMs / totalDuration) * 100)));

    let remainingText = '';
    if (isExpired) {
      remainingText = 'Expired';
    } else {
      const hours = Math.floor(remainingMs / (1000 * 60 * 60));
      const mins = Math.floor((remainingMs % (1000 * 60 * 60)) / (1000 * 60));
      const days = Math.floor(hours / 24);
      if (days > 0) {
        remainingText = `${days}d ${hours % 24}h remaining`;
      } else if (hours > 0) {
        remainingText = `${hours}h ${mins}m remaining`;
      } else {
        remainingText = `${Math.max(1, mins)}m remaining`;
      }
    }

    return {
      remainingMs,
      isExpired,
      isCritical,
      isSoon,
      progressPercent,
      remainingText,
    };
  };

  // Filtered leases
  const filteredLeases = useMemo(() => {
    return leases.filter((lease) => {
      // Role filter
      if (roleFilter !== 'all' && lease.role !== roleFilter) return false;

      // Status filter
      const { isCritical, isSoon } = getLeaseMetrics(lease);
      if (statusFilter === 'critical' && !isCritical) return false;
      if (statusFilter === 'soon' && !isSoon && !isCritical) return false;
      if (statusFilter === 'normal' && (isCritical || isSoon)) return false;

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchUser = lease.user_name.toLowerCase().includes(q) || String(lease.user_pk).includes(q);
        const matchApp = lease.app_name.toLowerCase().includes(q);
        if (!matchUser && !matchApp) return false;
      }

      return true;
    });
  }, [leases, roleFilter, statusFilter, searchQuery, nowMs]);

  // Summary counts
  const summary = useMemo(() => {
    let criticalCount = 0;
    let soonCount = 0;
    const uniqueUserPks = new Set<number>();

    leases.forEach((lease) => {
      uniqueUserPks.add(lease.user_pk);
      const { isCritical, isSoon } = getLeaseMetrics(lease);
      if (isCritical) criticalCount++;
      if (isSoon) soonCount++;
    });

    return {
      total: leases.length,
      critical: criticalCount,
      soon: soonCount,
      uniqueUsers: uniqueUserPks.size,
    };
  }, [leases, nowMs]);

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateError(null);

    if (!selectedUserPk) {
      setCreateError('Please select a user.');
      return;
    }
    if (!selectedAppPk) {
      setCreateError('Please select a service.');
      return;
    }

    const targetUser = users.find((u) => u.pk === Number(selectedUserPk));
    const targetApp = apps.find((a) => a.pk === selectedAppPk);

    if (!targetUser || !targetApp) {
      setCreateError('Invalid user or service selection.');
      return;
    }

    // Determine the right Authentik group for the chosen role
    let targetGroupPk = '';
    if (selectedRole === 'admin') {
      targetGroupPk = targetApp.granular_admin_group_pk || targetApp.bound_group_pk || '';
    } else {
      targetGroupPk = targetApp.granular_user_group_pk || targetApp.bound_group_pk || '';
    }

    if (!targetGroupPk) {
      setCreateError(`Service '${targetApp.name}' does not have a managed ${selectedRole} group bound. Please provision the service first.`);
      return;
    }

    const duration = customHours ? parseInt(customHours, 10) : selectedDurationHours;
    if (isNaN(duration) || duration <= 0) {
      setCreateError('Please enter a valid positive duration in hours.');
      return;
    }

    setSubmittingCreate(true);
    try {
      await onCreateLease({
        user_pk: targetUser.pk,
        user_name: targetUser.name || targetUser.username,
        app_pk: targetApp.pk,
        app_name: targetApp.name,
        group_pk: targetGroupPk,
        role: selectedRole,
        duration_hours: duration,
      });
      setIsCreateModalOpen(false);
      setSelectedUserPk('');
      setSelectedAppPk('');
      setSelectedRole('member');
      setSelectedDurationHours(24);
      setCustomHours('');
    } catch (err: any) {
      setCreateError(err.message || 'Failed to grant temporary lease');
    } finally {
      setSubmittingCreate(false);
    }
  };

  const handleExtend = async (lease: ExpiringGrant, hours: number) => {
    const key = `${lease.user_pk}-${lease.app_pk}`;
    setActionInProgress(key);
    try {
      await onExtendLease({
        user_pk: lease.user_pk,
        app_pk: lease.app_pk,
        group_pk: lease.group_pk,
        additional_hours: hours,
      });
    } finally {
      setActionInProgress(null);
    }
  };

  const handleConfirmRevoke = async (lease: ExpiringGrant) => {
    const key = `${lease.user_pk}-${lease.app_pk}`;
    setActionInProgress(key);
    try {
      await onRevokeLease(lease.user_pk, lease.app_pk, lease.group_pk);
      setRevokingLeaseKey(null);
    } finally {
      setActionInProgress(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header and Action Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-[#111827] border border-[#25354b] p-5 rounded-xl shadow-sm">
        <div>
          <div className="flex items-center space-x-2.5">
            <div className="h-8 w-8 rounded-lg bg-orange-500/10 border border-orange-500/30 flex items-center justify-center">
              <Clock className="h-4 w-4 text-[#fd7e14]" />
            </div>
            <h1 className="text-lg font-bold text-white tracking-tight">Active Leases & Temporary Access</h1>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            Monitor, extend, and revoke time-limited role grants across all your Authentik services.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={onRefresh}
            disabled={loading}
            className="flex items-center space-x-1.5 px-3 py-2 bg-[#16202e] hover:bg-[#1e2c3f] border border-[#25354b] text-slate-300 hover:text-white rounded-lg text-xs font-medium transition-colors"
            title="Refresh active leases"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin text-[#fd7e14]' : ''}`} />
            <span>Refresh</span>
          </button>

          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="flex items-center space-x-1.5 px-3.5 py-2 bg-[#fd7e14] hover:bg-[#ea6c0a] text-white rounded-lg text-xs font-semibold shadow-md shadow-orange-500/10 transition-colors"
          >
            <Plus className="h-3.5 w-3.5 stroke-[2.5]" />
            <span>Grant Temporary Access</span>
          </button>
        </div>
      </div>

      {/* Overview Stat Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
        <div className="bg-[#111827] border border-[#25354b] p-3.5 rounded-xl">
          <div className="text-[11px] font-medium text-slate-400">Total Active Leases</div>
          <div className="mt-1 flex items-baseline justify-between">
            <span className="text-2xl font-bold text-white tracking-tight">{summary.total}</span>
            <Clock className="h-4 w-4 text-cyan-400" />
          </div>
        </div>

        <div className="bg-[#111827] border border-[#25354b] p-3.5 rounded-xl">
          <div className="text-[11px] font-medium text-slate-400">Expiring Soon (&lt; 24h)</div>
          <div className="mt-1 flex items-baseline justify-between">
            <span className={`text-2xl font-bold tracking-tight ${summary.soon > 0 ? 'text-amber-400' : 'text-slate-300'}`}>
              {summary.soon}
            </span>
            <AlertTriangle className="h-4 w-4 text-amber-400" />
          </div>
        </div>

        <div className="bg-[#111827] border border-[#25354b] p-3.5 rounded-xl">
          <div className="text-[11px] font-medium text-slate-400">Critical (&lt; 2h)</div>
          <div className="mt-1 flex items-baseline justify-between">
            <span className={`text-2xl font-bold tracking-tight ${summary.critical > 0 ? 'text-rose-400' : 'text-slate-300'}`}>
              {summary.critical}
            </span>
            <Timer className="h-4 w-4 text-rose-400" />
          </div>
        </div>

        <div className="bg-[#111827] border border-[#25354b] p-3.5 rounded-xl">
          <div className="text-[11px] font-medium text-slate-400">Users with Leases</div>
          <div className="mt-1 flex items-baseline justify-between">
            <span className="text-2xl font-bold text-white tracking-tight">{summary.uniqueUsers}</span>
            <UserIcon className="h-4 w-4 text-emerald-400" />
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-[#111827] border border-[#25354b] p-3.5 rounded-xl flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-1 items-center gap-3 min-w-[240px]">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-500" />
            <input
              type="text"
              placeholder="Search by user or service..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-[#16202e] border border-[#25354b] rounded-lg pl-9 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-[#fd7e14] transition-colors"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2.5 top-2.5 text-slate-400 hover:text-white"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as any)}
            className="bg-[#16202e] border border-[#25354b] text-xs text-slate-300 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-[#fd7e14]"
          >
            <option value="all">All Statuses</option>
            <option value="critical">Critical (&lt; 2h)</option>
            <option value="soon">Expiring Soon (&lt; 24h)</option>
            <option value="normal">Normal (&gt; 24h)</option>
          </select>

          {/* Role Filter */}
          <select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value as any)}
            className="bg-[#16202e] border border-[#25354b] text-xs text-slate-300 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-[#fd7e14]"
          >
            <option value="all">All Roles</option>
            <option value="member">Member</option>
            <option value="admin">Admin</option>
          </select>
        </div>

        <div className="text-xs text-slate-400">
          Showing <strong className="text-white">{filteredLeases.length}</strong> of {leases.length} lease(s)
        </div>
      </div>

      {/* Leases Table / Cards */}
      {filteredLeases.length === 0 ? (
        <div className="bg-[#111827] border border-[#25354b] rounded-xl p-12 text-center">
          <div className="h-12 w-12 rounded-full bg-slate-800 border border-[#25354b] flex items-center justify-center mx-auto mb-3">
            <Clock className="h-6 w-6 text-slate-500" />
          </div>
          <h3 className="text-sm font-semibold text-white">No temporary leases found</h3>
          <p className="mt-1 text-xs text-slate-400 max-w-sm mx-auto">
            {leases.length === 0
              ? 'There are currently no active temporary access grants. You can grant expiring access to any user on any service.'
              : 'No active leases matched your current search filters.'}
          </p>
          {leases.length === 0 && (
            <button
              onClick={() => setIsCreateModalOpen(true)}
              className="mt-4 inline-flex items-center space-x-1.5 px-3.5 py-2 bg-[#fd7e14] hover:bg-[#ea6c0a] text-white rounded-lg text-xs font-semibold shadow transition-colors"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>Grant First Lease</span>
            </button>
          )}
        </div>
      ) : (
        <div className="bg-[#111827] border border-[#25354b] rounded-xl overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-[#0d131f] border-b border-[#25354b] text-slate-400 font-semibold uppercase tracking-wider text-[10px]">
                  <th className="py-3 px-4">User</th>
                  <th className="py-3 px-4">Service</th>
                  <th className="py-3 px-4">Role</th>
                  <th className="py-3 px-4">Time Remaining</th>
                  <th className="py-3 px-4">Expires At</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1e2c3f]">
                {filteredLeases.map((lease) => {
                  const leaseKey = `${lease.user_pk}-${lease.app_pk}`;
                  const isActionBusy = actionInProgress === leaseKey;
                  const isRevokeConfirm = revokingLeaseKey === leaseKey;
                  const { isCritical, isSoon, remainingText, progressPercent } = getLeaseMetrics(lease);
                  
                  // Look up user details if available
                  const userObj = users.find((u) => u.pk === lease.user_pk);
                  const appObj = apps.find((a) => a.pk === lease.app_pk);

                  const expDate = new Date(lease.expires_at);
                  const formattedExp = !isNaN(expDate.getTime())
                    ? expDate.toLocaleString(undefined, {
                        month: 'short',
                        day: 'numeric',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })
                    : lease.expires_at;

                  return (
                    <tr key={leaseKey} className="hover:bg-[#16202e]/60 transition-colors">
                      {/* User Column */}
                      <td className="py-3 px-4">
                        <div className="flex items-center space-x-3">
                          <img
                            src={userObj?.avatar || `https://api.dicebear.com/7.x/bottts/svg?seed=${lease.user_name}`}
                            alt={lease.user_name}
                            className="h-7 w-7 rounded-full bg-slate-800 border border-[#25354b] shrink-0"
                          />
                          <div className="min-w-0">
                            <div className="font-semibold text-white truncate flex items-center gap-1.5">
                              <span>{lease.user_name}</span>
                              <span className="text-[10px] text-slate-400 font-mono font-normal">#{lease.user_pk}</span>
                            </div>
                            <div className="text-[11px] text-slate-400 truncate">
                              {userObj?.email || userObj?.username || `User #${lease.user_pk}`}
                            </div>
                          </div>
                        </div>
                      </td>

                      {/* Service Column */}
                      <td className="py-3 px-4">
                        <div className="flex items-center space-x-2.5">
                          {appObj?.meta_icon ? (
                            <img
                              src={appObj.meta_icon}
                              alt={lease.app_name}
                              className="h-6 w-6 rounded shrink-0 object-contain"
                              onError={(e) => {
                                (e.target as HTMLElement).style.display = 'none';
                              }}
                            />
                          ) : (
                            <div className="h-6 w-6 rounded bg-[#1e2c3f] flex items-center justify-center shrink-0 text-slate-400">
                              <Server className="h-3.5 w-3.5" />
                            </div>
                          )}
                          <div className="min-w-0">
                            <div className="font-semibold text-white truncate">{lease.app_name}</div>
                            {appObj?.group && (
                              <div className="text-[10px] text-slate-400 truncate">{appObj.group}</div>
                            )}
                          </div>
                        </div>
                      </td>

                      {/* Role Column */}
                      <td className="py-3 px-4">
                        {lease.role === 'admin' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30">
                            <Crown className="h-3 w-3 text-amber-400" />
                            <span>Admin</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-sky-500/15 text-sky-300 border border-sky-500/30">
                            <ShieldCheck className="h-3 w-3 text-sky-400" />
                            <span>Member</span>
                          </span>
                        )}
                      </td>

                      {/* Time Remaining & Progress */}
                      <td className="py-3 px-4">
                        <div className="min-w-[150px]">
                          <div className="flex items-center justify-between mb-1">
                            <span
                              className={`text-xs font-semibold flex items-center gap-1.5 ${
                                isCritical
                                  ? 'text-rose-400 animate-pulse'
                                  : isSoon
                                  ? 'text-amber-400'
                                  : 'text-emerald-400'
                              }`}
                            >
                              <Clock className="h-3.5 w-3.5 shrink-0" />
                              <span>{remainingText}</span>
                            </span>
                            <span className="text-[10px] text-slate-500 font-mono">{progressPercent}%</span>
                          </div>
                          {/* Mini Progress Bar */}
                          <div className="w-full bg-[#1e2c3f] rounded-full h-1.5 overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-300 ${
                                isCritical ? 'bg-rose-500' : isSoon ? 'bg-amber-400' : 'bg-emerald-400'
                              }`}
                              style={{ width: `${progressPercent}%` }}
                            />
                          </div>
                        </div>
                      </td>

                      {/* Expires At Date */}
                      <td className="py-3 px-4 text-slate-300 text-[11px] font-mono">
                        <div>{formattedExp}</div>
                        <div className="text-[10px] text-slate-500">
                          Created: {new Date(lease.created_at).toLocaleDateString()}
                        </div>
                      </td>

                      {/* Actions */}
                      <td className="py-3 px-4 text-right">
                        {isRevokeConfirm ? (
                          <div className="inline-flex items-center gap-1.5 bg-[#1e2c3f] p-1 rounded-lg border border-rose-500/40">
                            <span className="text-[10px] font-medium text-rose-300 pl-1">Revoke?</span>
                            <button
                              onClick={() => handleConfirmRevoke(lease)}
                              disabled={isActionBusy}
                              className="px-2 py-0.5 bg-rose-600 hover:bg-rose-700 text-white rounded text-[11px] font-semibold"
                            >
                              Yes
                            </button>
                            <button
                              onClick={() => setRevokingLeaseKey(null)}
                              disabled={isActionBusy}
                              className="px-1.5 py-0.5 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded text-[11px]"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <div className="inline-flex items-center space-x-1.5">
                            {/* Extend +24h */}
                            <button
                              onClick={() => handleExtend(lease, 24)}
                              disabled={isActionBusy}
                              className="px-2 py-1 bg-[#16202e] hover:bg-[#1e2c3f] border border-[#25354b] text-slate-300 hover:text-white rounded text-[11px] font-medium transition-colors"
                              title="Extend lease by +24 Hours"
                            >
                              +24h
                            </button>

                            {/* Extend +7d */}
                            <button
                              onClick={() => handleExtend(lease, 168)}
                              disabled={isActionBusy}
                              className="px-2 py-1 bg-[#16202e] hover:bg-[#1e2c3f] border border-[#25354b] text-slate-300 hover:text-white rounded text-[11px] font-medium transition-colors"
                              title="Extend lease by +7 Days"
                            >
                              +7d
                            </button>

                            {/* Revoke Button */}
                            <button
                              onClick={() => setRevokingLeaseKey(leaseKey)}
                              disabled={isActionBusy}
                              className="p-1 rounded text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                              title="Revoke lease immediately"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Grant Temporary Access Modal */}
      {isCreateModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="bg-[#111827] border border-[#25354b] rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-5 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between pb-3 border-b border-[#25354b]">
              <div className="flex items-center space-x-2">
                <div className="h-7 w-7 rounded bg-orange-500/10 border border-orange-500/30 flex items-center justify-center">
                  <Clock className="h-4 w-4 text-[#fd7e14]" />
                </div>
                <h3 className="text-base font-bold text-white">Grant Temporary Access</h3>
              </div>
              <button
                onClick={() => setIsCreateModalOpen(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-[#16202e]"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {createError && (
              <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0 text-rose-400" />
                <span>{createError}</span>
              </div>
            )}

            <form onSubmit={handleCreateSubmit} className="space-y-4 text-xs">
              {/* Select User */}
              <div>
                <label className="block font-semibold text-slate-300 mb-1.5">
                  Target User <span className="text-rose-400">*</span>
                </label>
                <select
                  value={selectedUserPk}
                  onChange={(e) => setSelectedUserPk(e.target.value ? Number(e.target.value) : '')}
                  required
                  className="w-full bg-[#16202e] border border-[#25354b] rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#fd7e14]"
                >
                  <option value="">-- Select a User --</option>
                  {users.map((u) => (
                    <option key={u.pk} value={u.pk}>
                      {u.name || u.username} (@{u.username}) #{u.pk}
                    </option>
                  ))}
                </select>
              </div>

              {/* Select Application */}
              <div>
                <label className="block font-semibold text-slate-300 mb-1.5">
                  Target Service <span className="text-rose-400">*</span>
                </label>
                <select
                  value={selectedAppPk}
                  onChange={(e) => setSelectedAppPk(e.target.value)}
                  required
                  className="w-full bg-[#16202e] border border-[#25354b] rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#fd7e14]"
                >
                  <option value="">-- Select a Service --</option>
                  {apps.map((app) => (
                    <option key={app.pk} value={app.pk}>
                      {app.name} {app.group ? `(${app.group})` : ''} {!app.is_protected ? '⚠️ Unprotected' : ''}
                    </option>
                  ))}
                </select>
              </div>

              {/* Select Role */}
              <div>
                <label className="block font-semibold text-slate-300 mb-1.5">Role Level</label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => setSelectedRole('member')}
                    className={`flex items-center justify-center space-x-2 py-2 px-3 rounded-lg border font-medium transition-all ${
                      selectedRole === 'member'
                        ? 'bg-sky-500/15 border-sky-500/40 text-sky-300 font-semibold shadow-sm'
                        : 'bg-[#16202e] border-[#25354b] text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <ShieldCheck className="h-4 w-4 text-sky-400" />
                    <span>Member Access</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setSelectedRole('admin')}
                    className={`flex items-center justify-center space-x-2 py-2 px-3 rounded-lg border font-medium transition-all ${
                      selectedRole === 'admin'
                        ? 'bg-amber-500/15 border-amber-500/40 text-amber-300 font-semibold shadow-sm'
                        : 'bg-[#16202e] border-[#25354b] text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <Crown className="h-4 w-4 text-amber-400" />
                    <span>Admin Access</span>
                  </button>
                </div>
              </div>

              {/* Lease Duration Presets */}
              <div>
                <label className="block font-semibold text-slate-300 mb-1.5">Lease Duration</label>
                <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 mb-2">
                  {[
                    { label: '1 Hour', hours: 1 },
                    { label: '12 Hours', hours: 12 },
                    { label: '24 Hours', hours: 24 },
                    { label: '3 Days', hours: 72 },
                    { label: '7 Days', hours: 168 },
                    { label: '30 Days', hours: 720 },
                  ].map((preset) => (
                    <button
                      key={preset.hours}
                      type="button"
                      onClick={() => {
                        setSelectedDurationHours(preset.hours);
                        setCustomHours('');
                      }}
                      className={`py-1.5 px-2 rounded-lg text-center text-[11px] font-medium border transition-colors ${
                        !customHours && selectedDurationHours === preset.hours
                          ? 'bg-[#fd7e14] border-[#fd7e14] text-white font-semibold'
                          : 'bg-[#16202e] border-[#25354b] text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>

                <div className="flex items-center gap-2 mt-2">
                  <span className="text-slate-400 text-[11px]">Or custom hours:</span>
                  <input
                    type="number"
                    min="1"
                    max="87600"
                    placeholder="e.g. 48"
                    value={customHours}
                    onChange={(e) => setCustomHours(e.target.value)}
                    className="w-24 bg-[#16202e] border border-[#25354b] rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-[#fd7e14]"
                  />
                  <span className="text-slate-500 text-[11px]">hours</span>
                </div>
              </div>

              {/* Modal Buttons */}
              <div className="pt-3 border-t border-[#25354b] flex items-center justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setIsCreateModalOpen(false)}
                  disabled={submittingCreate}
                  className="px-3.5 py-2 rounded-lg bg-[#16202e] hover:bg-[#1e2c3f] border border-[#25354b] text-slate-300 hover:text-white font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingCreate}
                  className="px-4 py-2 rounded-lg bg-[#fd7e14] hover:bg-[#ea6c0a] text-white font-semibold shadow-md shadow-orange-500/10 flex items-center space-x-1.5"
                >
                  {submittingCreate ? (
                    <>
                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                      <span>Provisioning...</span>
                    </>
                  ) : (
                    <>
                      <Clock className="h-3.5 w-3.5" />
                      <span>Grant Lease</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
