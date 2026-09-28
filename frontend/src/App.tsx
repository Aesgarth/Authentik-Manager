import React, { useState, useEffect, useCallback } from 'react';
import { api } from './api/client';
import { 
  AccessMatrixData, 
  HealthStatus, 
  AuthStatus, 
  TrackedInvite, 
  AuditLog, 
  StagedChange, 
  User, 
  Application,
  WhatsAppStatus,
  AccessTemplate
} from './types';
import { Sidebar } from './components/Sidebar';
import { OverviewCards } from './components/OverviewCards';
import { SecurityBanner } from './components/SecurityBanner';
import { AccessMatrix } from './components/AccessMatrix';
import { InviteList } from './components/InviteList';
import { InviteModal } from './components/InviteModal';
import { ProvisionModal } from './components/ProvisionModal';
import { AuditLogDrawer } from './components/AuditLogDrawer';
import { FlowGuideModal } from './components/FlowGuideModal';
import { WhatsAppModal } from './components/WhatsAppModal';
import { TemplateModal } from './components/TemplateModal';
import { SettingsPanel } from './components/SettingsPanel';
import { Lock, AlertCircle, CheckCircle } from 'lucide-react';

export const App: React.FC = () => {
  const [matrixData, setMatrixData] = useState<AccessMatrixData | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [whatsAppStatus, setWhatsAppStatus] = useState<WhatsAppStatus | null>(null);
  const [invites, setInvites] = useState<TrackedInvite[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [flowGuide, setFlowGuide] = useState<{ title: string; description: string; snippet: string } | null>(null);

  const [activeTab, setActiveTab] = useState<'matrix' | 'invites' | 'audit' | 'settings'>('matrix');
  const [stagedMode, setStagedMode] = useState<boolean>(false);
  const [stagedChanges, setStagedChanges] = useState<StagedChange[]>([]);
  const [loading, setLoading] = useState<boolean>(false);

  // Modals
  const [isInviteModalOpen, setIsInviteModalOpen] = useState(false);
  const [isProvisionModalOpen, setIsProvisionModalOpen] = useState(false);
  const [isGuideModalOpen, setIsGuideModalOpen] = useState(false);
  const [isAuditDrawerOpen, setIsAuditDrawerOpen] = useState(false);
  const [isWhatsAppModalOpen, setIsWhatsAppModalOpen] = useState(false);
  const [isTemplateModalOpen, setIsTemplateModalOpen] = useState(false);

  // Role Presets / Personas
  const [templates, setTemplates] = useState<AccessTemplate[]>([]);

  // Password Login state
  const [loginPassword, setLoginPassword] = useState('');
  const [loginError, setLoginError] = useState<string | null>(null);

  // Toast
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);

  const showToast = (message: string, type: 'success' | 'error' | 'info' = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3500);
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [matrix, h, a, invs, logs, guide, wa, tmpls] = await Promise.all([
        api.getMatrix(),
        api.getHealth(),
        api.getAuthStatus(),
        api.getInvites(),
        api.getAuditLogs(50),
        api.getExpressionPolicySnippet(),
        api.getWhatsAppStatus().catch(() => null),
        api.getTemplates().catch(() => []),
      ]);
      setMatrixData(matrix);
      setHealth(h);
      setAuth(a);
      setInvites(invs);
      setAuditLogs(logs);
      setFlowGuide(guide);
      if (wa) setWhatsAppStatus(wa);
      if (tmpls) setTemplates(tmpls);
    } catch (err: any) {
      console.error('Failed to load data:', err);
      showToast(err.message || 'Failed to connect to backend', 'error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Periodic poll for WhatsApp status when modal is open
  useEffect(() => {
    if (!isWhatsAppModalOpen) return;
    const interval = setInterval(() => {
      api.getWhatsAppStatus().then(setWhatsAppStatus).catch(() => {});
    }, 4000);
    return () => clearInterval(interval);
  }, [isWhatsAppModalOpen]);

  // Unified Set Role Handler (supports None, Member, Administrator in both Instant and Staged modes, plus Expiring Leases)
  const handleSetRole = async (
    user: User, 
    app: Application, 
    targetRole: 'none' | 'member' | 'admin',
    durationHours?: number
  ) => {
    const userGroupPk = app.granular_user_group_pk || app.bound_group_pk || matrixData?.app_group_map[app.pk];
    let adminGroupPk = app.granular_admin_group_pk || matrixData?.app_admin_group_map?.[app.pk];

    if (!userGroupPk && targetRole !== 'none') {
      setIsProvisionModalOpen(true);
      return;
    }

    // Auto-provision admin group if user selected 'admin' but app does not have one yet
    if (targetRole === 'admin' && !adminGroupPk) {
      try {
        setLoading(true);
        showToast(`Provisioning admin group for ${app.name}...`, 'info');
        const res = await api.provisionApp(app.pk, { create_user_group: true, create_admin_group: true });
        adminGroupPk = res.admin_group_pk;
        await loadData();
      } catch (err: any) {
        showToast(`Failed to provision admin group: ${err.message}`, 'error');
        setLoading(false);
        return;
      }
    }

    const uPkStr = String(user.pk);
    const isDirectMember = Boolean(
      userGroupPk && (
        user.groups.includes(userGroupPk) ||
        matrixData?.permissions[uPkStr]?.[app.pk]
      )
    );
    const isDirectAdmin = Boolean(
      adminGroupPk && (
        user.groups.includes(adminGroupPk) ||
        matrixData?.admin_permissions?.[uPkStr]?.[app.pk]
      )
    );

    let grantUser: boolean | null = null;
    let grantAdmin: boolean | null = null;

    if (targetRole === 'none') {
      if (isDirectMember && userGroupPk) grantUser = false;
      if (isDirectAdmin && adminGroupPk) grantAdmin = false;
    } else if (targetRole === 'member') {
      if (!isDirectMember && userGroupPk) grantUser = true;
      if (isDirectAdmin && adminGroupPk) grantAdmin = false;
    } else if (targetRole === 'admin') {
      if (!isDirectAdmin && adminGroupPk) grantAdmin = true;
      if (!isDirectMember && userGroupPk) grantUser = true;
    }

    if (grantUser === null && grantAdmin === null && !durationHours) {
      return; // Already in target role without a duration change
    }

    if (stagedMode) {
      // Stage the changes
      setStagedChanges((prev) => {
        let updated = [...prev];
        if (grantUser !== null && userGroupPk) {
          const idx = updated.findIndex(c => c.user_pk === user.pk && c.app_pk === app.pk && c.group_pk === userGroupPk);
          if (idx >= 0) {
            updated[idx] = { ...updated[idx], grant: grantUser, duration_hours: durationHours };
          } else {
            updated.push({
              user_pk: user.pk,
              userName: user.name,
              app_pk: app.pk,
              appName: app.name,
              group_pk: userGroupPk,
              grant: grantUser,
              duration_hours: durationHours,
            });
          }
        }
        if (grantAdmin !== null && adminGroupPk) {
          const idx = updated.findIndex(c => c.user_pk === user.pk && c.app_pk === app.pk && c.group_pk === adminGroupPk);
          if (idx >= 0) {
            updated[idx] = { ...updated[idx], grant: grantAdmin, duration_hours: durationHours };
          } else {
            updated.push({
              user_pk: user.pk,
              userName: user.name,
              app_pk: app.pk,
              appName: `${app.name} [Admin]`,
              group_pk: adminGroupPk,
              grant: grantAdmin,
              duration_hours: durationHours,
            });
          }
        }
        return updated;
      });
      showToast(`Staged role update for ${user.name} on ${app.name}`, 'info');
    } else {
      // Instant Mode: execute immediately with optimistic UI
      try {
        setLoading(true);
        setMatrixData((prev) => {
          if (!prev) return prev;
          const uStr = String(user.pk);
          const nextPerms = { ...prev.permissions[uStr] };
          const nextAdminPerms = { ...(prev.admin_permissions?.[uStr] || {}) };
          const nextExpiringAll = { ...(prev.expiring_grants || {}) };
          const nextUserExpiring = { ...(nextExpiringAll[uStr] || {}) };

          if (targetRole === 'none') {
            nextPerms[app.pk] = false;
            nextAdminPerms[app.pk] = false;
            delete nextUserExpiring[app.pk];
          } else if (targetRole === 'member') {
            nextPerms[app.pk] = true;
            nextAdminPerms[app.pk] = false;
          } else if (targetRole === 'admin') {
            nextPerms[app.pk] = true;
            nextAdminPerms[app.pk] = true;
          }

          const updatedUsers = prev.users.map(u => {
            if (u.pk !== user.pk) return u;
            const gSet = new Set(u.groups);
            if (grantUser === true && userGroupPk) gSet.add(userGroupPk);
            if (grantUser === false && userGroupPk) gSet.delete(userGroupPk);
            if (grantAdmin === true && adminGroupPk) gSet.add(adminGroupPk);
            if (grantAdmin === false && adminGroupPk) gSet.delete(adminGroupPk);
            return { ...u, groups: Array.from(gSet) };
          });

          nextExpiringAll[uStr] = nextUserExpiring;

          return {
            ...prev,
            users: updatedUsers,
            permissions: { ...prev.permissions, [uStr]: nextPerms },
            admin_permissions: { ...(prev.admin_permissions || {}), [uStr]: nextAdminPerms },
            expiring_grants: nextExpiringAll,
          };
        });

        if (durationHours && targetRole !== 'none') {
          const groupToGrant = targetRole === 'admin' ? adminGroupPk! : userGroupPk!;
          const lease = await api.createLease({
            user_pk: user.pk,
            user_name: user.name,
            app_pk: app.pk,
            app_name: app.name,
            group_pk: groupToGrant,
            role: targetRole,
            duration_hours: durationHours,
          });
          setMatrixData(prev => {
            if (!prev) return prev;
            const uStr = String(user.pk);
            const nextAll = { ...(prev.expiring_grants || {}) };
            const nextUser = { ...(nextAll[uStr] || {}) };
            nextUser[app.pk] = lease;
            nextAll[uStr] = nextUser;
            return { ...prev, expiring_grants: nextAll };
          });
        } else {
          if (grantAdmin !== null && adminGroupPk) {
            await api.togglePermission(user.pk, app.pk, adminGroupPk, grantAdmin);
          }
          if (grantUser !== null && userGroupPk) {
            await api.togglePermission(user.pk, app.pk, userGroupPk, grantUser);
          }
        }

        const roleLabel = targetRole === 'admin' ? 'Administrator' : targetRole === 'member' ? 'Member' : 'No Access';
        const suffix = durationHours ? ` (${durationHours}h lease)` : '';
        showToast(`Updated ${user.name} on ${app.name} to ${roleLabel}${suffix}`, 'success');

        api.getHealth().then(setHealth);
        api.getAuditLogs(50).then(setAuditLogs);
      } catch (err: any) {
        showToast(`Failed: ${err.message}`, 'error');
        await loadData();
      } finally {
        setLoading(false);
      }
    }
  };

  // Role Preset (Template) Actions
  const handleCreateTemplate = async (params: {
    name: string;
    description?: string;
    icon?: string;
    assignments: Record<string, string>;
  }) => {
    try {
      const created = await api.createTemplate(params);
      setTemplates((prev) => [...prev, created]);
      showToast(`Created role preset "${created.name}"`, 'success');
    } catch (err: any) {
      showToast(err.message || 'Failed to create role preset', 'error');
      throw err;
    }
  };

  const handleDeleteTemplate = async (templateId: number) => {
    try {
      await api.deleteTemplate(templateId);
      setTemplates((prev) => prev.filter((t) => t.id !== templateId));
      showToast('Role preset deleted', 'info');
    } catch (err: any) {
      showToast(err.message || 'Failed to delete role preset', 'error');
      throw err;
    }
  };

  const handleApplyTemplate = async (templateId: number, params: {
    user_pk: number;
    user_name: string;
    duration_hours?: number;
  }) => {
    try {
      setLoading(true);
      const res = await api.applyTemplate(templateId, params);
      showToast(`Applied preset! (${res.applied_count} grants configured)`, 'success');
      setIsTemplateModalOpen(false);
      await loadData();
    } catch (err: any) {
      showToast(err.message || 'Failed to apply preset', 'error');
      throw err;
    } finally {
      setLoading(false);
    }
  };

  // Commit all staged changes
  const handleApplyStagedChanges = async () => {
    if (stagedChanges.length === 0) return;
    setLoading(true);
    try {
      const res = await api.bulkTogglePermissions(stagedChanges);
      showToast(`Successfully applied ${res.succeeded} permission change(s)!`, 'success');
      setStagedChanges([]);
      await loadData();
    } catch (err: any) {
      showToast(`Error applying changes: ${err.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDiscardStagedChanges = () => {
    setStagedChanges([]);
    showToast('Discarded all staged changes', 'info');
  };

  // Provisioning
  const handleProvisionApp = async (appPk: string, options?: any) => {
    setLoading(true);
    try {
      const opts = typeof options === 'string' ? { group_name: options } : options;
      const res = await api.provisionApp(appPk, opts);
      showToast(`Configured granular groups for ${res.app_name}!`, 'success');
      await loadData();
      return res;
    } catch (err: any) {
      showToast(err.message, 'error');
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const handleProvisionAll = async (options?: any) => {
    setLoading(true);
    try {
      const res = await api.provisionAll(options);
      showToast(`Provisioned granular groups across ${res.provisioned_count} application(s)!`, 'success');
      await loadData();
      return res;
    } catch (err: any) {
      showToast(err.message, 'error');
      throw err;
    } finally {
      setLoading(false);
    }
  };

  // Toggle User Active
  const handleToggleUserActive = async (userPk: number) => {
    try {
      const res = await api.toggleUserActive(userPk);
      showToast(`User account ${res.is_active ? 'activated' : 'suspended'}`, 'info');
      await loadData();
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  // Create & Revoke Invites
  const handleCreateInvite = async (params: any) => {
    const inv = await api.createInvite(params);
    showToast(`Created invitation for ${inv.name}`, 'success');
    const updated = await api.getInvites();
    setInvites(updated);
    api.getHealth().then(setHealth);
    api.getAuditLogs(50).then(setAuditLogs);
    return inv;
  };

  const handleRevokeInvite = async (invitationPk: string) => {
    try {
      await api.revokeInvite(invitationPk);
      showToast('Invitation revoked', 'info');
      const updated = await api.getInvites();
      setInvites(updated);
      api.getHealth().then(setHealth);
      api.getAuditLogs(50).then(setAuditLogs);
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleSyncRedemptions = async () => {
    try {
      const res = await fetch('/api/invites/sync', { method: 'POST' });
      const data = await res.json();
      showToast(`Sync completed: ${data.redeemed_count} new redemption(s) assigned`, 'info');
      await loadData();
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  // Password Login
  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setLoginError(null);
      await api.loginPassword(loginPassword);
      setLoginPassword('');
      await loadData();
    } catch (err: any) {
      setLoginError(err.message || 'Login failed');
    }
  };

  const handleLogout = async () => {
    await api.logout();
    await loadData();
  };

  const handleLogoutWhatsApp = async () => {
    try {
      await api.logoutWhatsApp();
      showToast('Disconnected WhatsApp session', 'info');
      const wa = await api.getWhatsAppStatus().catch(() => null);
      setWhatsAppStatus(wa);
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleSendWhatsAppMessage = async (recipient: string, message: string) => {
    return await api.sendWhatsAppMessage(recipient, message);
  };

  // Check unprotected apps
  const unprotectedApps = matrixData ? matrixData.apps.filter((a) => !a.is_protected) : [];

  return (
    <div className="min-h-screen bg-[#0b0f17] text-slate-100 flex flex-col md:flex-row font-sans selection:bg-orange-500/30 selection:text-orange-200">
      
      {/* Left Sidebar Toolbar */}
      <Sidebar
        health={health}
        auth={auth}
        whatsAppStatus={whatsAppStatus}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        stagedMode={stagedMode}
        setStagedMode={setStagedMode}
        onRefresh={loadData}
        onOpenInviteModal={() => setIsInviteModalOpen(true)}
        onOpenGuideModal={() => setIsGuideModalOpen(true)}
        onOpenWhatsAppModal={() => setIsWhatsAppModalOpen(true)}
        onOpenTemplatesModal={() => setIsTemplateModalOpen(true)}
        onLogout={handleLogout}
        loading={loading}
      />

      {/* Main Content Area */}
      <main className="flex-1 min-w-0 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        
        {/* Unauthenticated Login Screen if password auth is active */}
        {auth && !auth.authenticated && auth.auth_method === 'password' && (
          <div className="max-w-md mx-auto my-16 bg-[#111827] border border-[#25354b] rounded-2xl p-6 shadow-2xl text-center">
            <div className="h-12 w-12 rounded-xl bg-orange-500/15 text-[#fd7e14] border border-orange-500/30 mx-auto flex items-center justify-center mb-4">
              <Lock className="h-6 w-6" />
            </div>
            <h2 className="text-lg font-bold text-white mb-1">authentik Administrator Login</h2>
            <p className="text-xs text-slate-400 mb-5">
              Enter your admin password to access the Authentik Access Manager.
            </p>
            {loginError && (
              <div className="p-3 mb-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs">
                {loginError}
              </div>
            )}
            <form onSubmit={handlePasswordLogin} className="space-y-3">
              <input
                type="password"
                placeholder="Enter password..."
                value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
                className="w-full bg-[#0b0f17] border border-[#25354b] rounded-xl px-4 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-[#fd7e14]"
                autoFocus
              />
              <button
                type="submit"
                className="w-full bg-[#fd7e14] hover:bg-[#ea6c0a] text-white text-xs font-semibold py-2.5 rounded-xl transition-colors shadow"
              >
                Sign In
              </button>
            </form>
          </div>
        )}

        {/* Normal Authenticated View */}
        {(!auth || auth.authenticated || auth.auth_method === 'none') && (
          <>
            {/* Authentik Connection Error Banner */}
            {health && !health.authentik_connected && !health.demo_mode && (
              <div className="mb-6 p-4 rounded-2xl bg-rose-500/10 border border-rose-500/30 flex items-start gap-3 text-rose-300 shadow-lg">
                <AlertCircle className="h-5 w-5 text-rose-400 shrink-0 mt-0.5" />
                <div className="text-xs space-y-1">
                  <div className="font-semibold text-rose-200">
                    Failed to connect to Authentik API at <span className="font-mono text-rose-300">{health.authentik_url}</span>
                  </div>
                  <p className="text-slate-300 font-mono text-[11px] bg-rose-950/40 p-2 rounded border border-rose-900/50">
                    {health.connection_error || 'Unable to authenticate with provided API token or host is unreachable.'}
                  </p>
                  <p className="text-slate-400 text-[11px] pt-1">
                    Check your <code className="text-rose-300 bg-rose-950/60 px-1 py-0.5 rounded">.env</code> configuration: ensure <code className="text-rose-300 bg-rose-950/60 px-1 py-0.5 rounded">AUTHENTIK_URL</code> and <code className="text-rose-300 bg-rose-950/60 px-1 py-0.5 rounded">AUTHENTIK_TOKEN</code> are valid and restart the container.
                  </p>
                </div>
              </div>
            )}

            {/* KPI Cards and Security Alerts (shown on operational tabs) */}
            {activeTab !== 'settings' && (
              <>
                <OverviewCards
                  health={health}
                  onOpenProvisionModal={() => setIsProvisionModalOpen(true)}
                  onOpenInviteList={() => setActiveTab('invites')}
                />

                <SecurityBanner
                  unprotectedApps={unprotectedApps}
                  onLockdown={handleProvisionAll}
                  loading={loading}
                />
              </>
            )}

            {/* Content Tabs */}
            {activeTab === 'matrix' && matrixData && (
              <AccessMatrix
                data={matrixData}
                stagedMode={stagedMode}
                stagedChanges={stagedChanges}
                onSetRole={handleSetRole}
                onApplyStagedChanges={handleApplyStagedChanges}
                onDiscardStagedChanges={handleDiscardStagedChanges}
                onToggleUserActive={handleToggleUserActive}
                onProvisionApp={() => setIsProvisionModalOpen(true)}
                onProvisionAll={handleProvisionAll}
                onOpenTemplates={() => setIsTemplateModalOpen(true)}
                loading={loading}
              />
            )}

            {activeTab === 'invites' && (
              <InviteList
                invites={invites}
                onOpenInviteModal={() => setIsInviteModalOpen(true)}
                onRevokeInvite={handleRevokeInvite}
                onSyncRedemptions={handleSyncRedemptions}
                loading={loading}
              />
            )}

            {activeTab === 'audit' && (
              <div className="bg-[#111827] border border-[#25354b] rounded-2xl p-4 shadow-xl">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h3 className="text-base font-bold text-white mb-0.5">Authentik Audit Trail</h3>
                    <p className="text-xs text-slate-400">Chronological security and permission changes.</p>
                  </div>
                </div>
                <div className="space-y-2">
                  {auditLogs.map((log) => (
                    <div
                      key={log.id}
                      className="bg-[#0b0f17] border border-[#25354b] rounded-xl p-3 flex items-center justify-between text-xs"
                    >
                      <div className="flex items-center space-x-2.5">
                        <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-orange-500/10 text-[#fd7e14] border border-orange-500/20 font-bold">
                          {log.action}
                        </span>
                        <span className="font-semibold text-slate-200">{log.target_name}</span>
                        {log.details && <span className="text-slate-400 text-[11px]">• {log.details}</span>}
                      </div>
                      <div className="text-[11px] text-slate-500 font-mono">
                        {new Date(log.timestamp).toLocaleString()} by {log.actor}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {activeTab === 'settings' && (
              <SettingsPanel
                onShowToast={showToast}
                onSettingsUpdated={loadData}
              />
            )}
          </>
        )}

      </main>

      {/* Modals */}
      {matrixData && (
        <>
          <InviteModal
            isOpen={isInviteModalOpen}
            onClose={() => setIsInviteModalOpen(false)}
            apps={matrixData.apps}
            appGroupMap={matrixData.app_group_map}
            templates={templates}
            isWhatsAppConnected={whatsAppStatus?.status === 'connected'}
            onCreateInvite={handleCreateInvite}
          />
          <ProvisionModal
            isOpen={isProvisionModalOpen}
            onClose={() => setIsProvisionModalOpen(false)}
            apps={matrixData.apps}
            onProvisionApp={handleProvisionApp}
            onProvisionAll={handleProvisionAll}
            loading={loading}
          />
          <TemplateModal
            isOpen={isTemplateModalOpen}
            onClose={() => setIsTemplateModalOpen(false)}
            templates={templates}
            apps={matrixData.apps}
            users={matrixData.users}
            onCreateTemplate={handleCreateTemplate}
            onDeleteTemplate={handleDeleteTemplate}
            onApplyTemplate={handleApplyTemplate}
            loading={loading}
          />
        </>
      )}

      <WhatsAppModal
        isOpen={isWhatsAppModalOpen}
        onClose={() => setIsWhatsAppModalOpen(false)}
        status={whatsAppStatus}
        onRefresh={async () => {
          const wa = await api.getWhatsAppStatus().catch(() => null);
          setWhatsAppStatus(wa);
        }}
        onLogout={handleLogoutWhatsApp}
        onSendMessage={handleSendWhatsAppMessage}
      />

      <FlowGuideModal
        isOpen={isGuideModalOpen}
        onClose={() => setIsGuideModalOpen(false)}
        flowGuide={flowGuide}
      />

      <AuditLogDrawer
        isOpen={isAuditDrawerOpen}
        onClose={() => setIsAuditDrawerOpen(false)}
        logs={auditLogs}
      />

      {/* Floating Toast Notification */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 animate-in fade-in slide-in-from-bottom-5">
          <div
            className={`px-4 py-3 rounded-xl shadow-2xl border text-xs font-medium flex items-center space-x-2.5 backdrop-blur-md ${
              toast.type === 'success'
                ? 'bg-[#111827] border-emerald-500/40 text-emerald-200'
                : toast.type === 'error'
                ? 'bg-[#111827] border-rose-500/40 text-rose-200'
                : 'bg-[#111827] border-orange-500/40 text-orange-200'
            }`}
          >
            {toast.type === 'success' && <CheckCircle className="h-4 w-4 text-emerald-400" />}
            {toast.type === 'error' && <AlertCircle className="h-4 w-4 text-rose-400" />}
            <span>{toast.message}</span>
          </div>
        </div>
      )}

    </div>
  );
};
