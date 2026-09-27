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
  WhatsAppStatus
} from './types';
import { Header } from './components/Header';
import { OverviewCards } from './components/OverviewCards';
import { SecurityBanner } from './components/SecurityBanner';
import { AccessMatrix } from './components/AccessMatrix';
import { InviteList } from './components/InviteList';
import { InviteModal } from './components/InviteModal';
import { ProvisionModal } from './components/ProvisionModal';
import { AuditLogDrawer } from './components/AuditLogDrawer';
import { FlowGuideModal } from './components/FlowGuideModal';
import { WhatsAppModal } from './components/WhatsAppModal';
import { Lock, AlertCircle, CheckCircle } from 'lucide-react';

export const App: React.FC = () => {
  const [matrixData, setMatrixData] = useState<AccessMatrixData | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [whatsAppStatus, setWhatsAppStatus] = useState<WhatsAppStatus | null>(null);
  const [invites, setInvites] = useState<TrackedInvite[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [flowGuide, setFlowGuide] = useState<{ title: string; description: string; snippet: string } | null>(null);

  const [activeTab, setActiveTab] = useState<'matrix' | 'invites' | 'audit'>('matrix');
  const [stagedMode, setStagedMode] = useState<boolean>(false);
  const [stagedChanges, setStagedChanges] = useState<StagedChange[]>([]);
  const [loading, setLoading] = useState<boolean>(false);

  // Modals
  const [isInviteModalOpen, setIsInviteModalOpen] = useState(false);
  const [isProvisionModalOpen, setIsProvisionModalOpen] = useState(false);
  const [isGuideModalOpen, setIsGuideModalOpen] = useState(false);
  const [isAuditDrawerOpen, setIsAuditDrawerOpen] = useState(false);
  const [isWhatsAppModalOpen, setIsWhatsAppModalOpen] = useState(false);

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
      const [matrix, h, a, invs, logs, guide, wa] = await Promise.all([
        api.getMatrix(),
        api.getHealth(),
        api.getAuthStatus(),
        api.getInvites(),
        api.getAuditLogs(50),
        api.getExpressionPolicySnippet(),
        api.getWhatsAppStatus().catch(() => null),
      ]);
      setMatrixData(matrix);
      setHealth(h);
      setAuth(a);
      setInvites(invs);
      setAuditLogs(logs);
      setFlowGuide(guide);
      if (wa) setWhatsAppStatus(wa);
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

  // Handle cell click (grant/revoke access)
  const handleToggleCell = async (user: User, app: Application, currentAccess: boolean) => {
    const groupPk = app.bound_group_pk || matrixData?.app_group_map[app.pk];
    if (!groupPk) {
      setIsProvisionModalOpen(true);
      return;
    }

    const newGrant = !currentAccess;

    if (stagedMode) {
      // Add to staged changes or revert if already staged
      setStagedChanges((prev) => {
        const existingIdx = prev.findIndex(
          (c) => c.user_pk === user.pk && c.app_pk === app.pk
        );
        if (existingIdx >= 0) {
          // If toggled back to original state, remove staged change
          const existing = prev[existingIdx];
          if (existing.grant === currentAccess) {
            return prev.filter((_, idx) => idx !== existingIdx);
          }
          const updated = [...prev];
          updated[existingIdx] = { ...existing, grant: newGrant };
          return updated;
        } else {
          return [
            ...prev,
            {
              user_pk: user.pk,
              userName: user.name,
              app_pk: app.pk,
              appName: app.name,
              group_pk: groupPk,
              grant: newGrant,
            },
          ];
        }
      });
    } else {
      // Instant Mode: Execute immediately with optimistic UI
      try {
        setMatrixData((prev) => {
          if (!prev) return prev;
          const uPkStr = String(user.pk);
          return {
            ...prev,
            permissions: {
              ...prev.permissions,
              [uPkStr]: {
                ...prev.permissions[uPkStr],
                [app.pk]: newGrant,
              },
            },
          };
        });

        await api.togglePermission(user.pk, app.pk, groupPk, newGrant);
        showToast(
          `${newGrant ? 'Granted' : 'Revoked'} ${user.name} access to ${app.name}`,
          'success'
        );
        
        // Refresh health & logs in background
        api.getHealth().then(setHealth);
        api.getAuditLogs(50).then(setAuditLogs);
      } catch (err: any) {
        showToast(`Failed: ${err.message}`, 'error');
        loadData(); // Revert
      }
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
  const handleProvisionApp = async (appPk: string, customGroupName?: string) => {
    setLoading(true);
    try {
      const res = await api.provisionApp(appPk, customGroupName);
      showToast(`Secured ${res.app_name} with group '${res.group_name}'!`, 'success');
      await loadData();
      return res;
    } catch (err: any) {
      showToast(err.message, 'error');
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const handleProvisionAll = async () => {
    setLoading(true);
    try {
      const res = await api.provisionAllUnprotected();
      showToast(`Secured ${res.provisioned_count} application(s)!`, 'success');
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
    <div className="min-h-screen bg-slate-950 flex flex-col">
      
      {/* Header */}
      <Header
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
        onOpenProvisionModal={() => setIsProvisionModalOpen(true)}
        onOpenWhatsAppModal={() => setIsWhatsAppModalOpen(true)}
        onLogout={handleLogout}
        loading={loading}
      />

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        
        {/* Unauthenticated Login Screen if password auth is active */}
        {auth && !auth.authenticated && auth.auth_method === 'password' && (
          <div className="max-w-md mx-auto my-16 bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl text-center">
            <div className="h-12 w-12 rounded-xl bg-indigo-600/20 text-indigo-400 mx-auto flex items-center justify-center mb-4">
              <Lock className="h-6 w-6" />
            </div>
            <h2 className="text-lg font-bold text-white mb-1">Administrator Login</h2>
            <p className="text-xs text-slate-400 mb-5">
              Enter the admin password to access Authentik Access Manager.
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
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-indigo-500"
                autoFocus
              />
              <button
                type="submit"
                className="w-full bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold py-2.5 rounded-xl transition-colors shadow"
              >
                Sign In
              </button>
            </form>
          </div>
        )}

        {/* Normal Authenticated View */}
        {(!auth || auth.authenticated || auth.auth_method === 'none') && (
          <>
            {/* KPI Cards */}
            <OverviewCards
              health={health}
              onOpenProvisionModal={() => setIsProvisionModalOpen(true)}
              onOpenInviteList={() => setActiveTab('invites')}
            />

            {/* Security Alert Banner for Open Services */}
            <SecurityBanner
              unprotectedApps={unprotectedApps}
              onLockdown={handleProvisionAll}
              loading={loading}
            />

            {/* Content Tabs */}
            {activeTab === 'matrix' && matrixData && (
              <AccessMatrix
                data={matrixData}
                stagedMode={stagedMode}
                stagedChanges={stagedChanges}
                onToggleCell={handleToggleCell}
                onApplyStagedChanges={handleApplyStagedChanges}
                onDiscardStagedChanges={handleDiscardStagedChanges}
                onToggleUserActive={handleToggleUserActive}
                onProvisionApp={(appPk) => handleProvisionApp(appPk)}
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
              <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-xl">
                <h3 className="text-base font-bold text-white mb-1">Audit Trail</h3>
                <p className="text-xs text-slate-400 mb-4">Complete security event log.</p>
                <div className="space-y-2">
                  {auditLogs.map((log) => (
                    <div
                      key={log.id}
                      className="bg-slate-950 border border-slate-800 rounded-xl p-3 flex items-center justify-between text-xs"
                    >
                      <div className="flex items-center space-x-2">
                        <span className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 font-bold">
                          {log.action}
                        </span>
                        <span className="font-semibold text-slate-200">{log.target_name}</span>
                        {log.details && <span className="text-slate-400 text-[11px]">• {log.details}</span>}
                      </div>
                      <div className="text-[11px] text-slate-500">
                        {new Date(log.timestamp).toLocaleString()} by {log.actor}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
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
                ? 'bg-emerald-950/90 border-emerald-500/40 text-emerald-200'
                : toast.type === 'error'
                ? 'bg-rose-950/90 border-rose-500/40 text-rose-200'
                : 'bg-indigo-950/90 border-indigo-500/40 text-indigo-200'
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
