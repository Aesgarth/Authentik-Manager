import React from 'react';
import { X, FileText, CheckCircle, XCircle } from 'lucide-react';
import { AuditLog } from '../types';

interface AuditLogDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  logs: AuditLog[];
}

export const AuditLogDrawer: React.FC<AuditLogDrawerProps> = ({
  isOpen,
  onClose,
  logs,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-3xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
        
        {/* Header */}
        <div className="p-5 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="h-9 w-9 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center">
              <FileText className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Security & Audit History</h3>
              <p className="text-xs text-slate-400">
                Immutable record of all access modifications, provisioning, and invitations.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Log List */}
        <div className="p-5 overflow-y-auto flex-1">
          {logs.length === 0 ? (
            <div className="text-center py-12 text-slate-500 text-xs">
              No audit logs recorded yet.
            </div>
          ) : (
            <div className="space-y-2">
              {logs.map((log) => {
                const isSuccess = log.status === 'SUCCESS';
                const isGrant = log.action.includes('GRANT');
                const isRevoke = log.action.includes('REVOKE');

                return (
                  <div
                    key={log.id}
                    className="bg-slate-950/80 border border-slate-800/80 rounded-xl p-3 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 text-xs"
                  >
                    <div className="flex items-start space-x-2.5">
                      <div className="mt-0.5">
                        {isSuccess ? (
                          <CheckCircle className="h-4 w-4 text-emerald-400" />
                        ) : (
                          <XCircle className="h-4 w-4 text-rose-400" />
                        )}
                      </div>
                      <div>
                        <div className="flex items-center space-x-2">
                          <span
                            className={`font-mono text-[11px] px-1.5 py-0.2 rounded font-semibold ${
                              isGrant
                                ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20'
                                : isRevoke
                                ? 'bg-rose-500/10 text-rose-300 border border-rose-500/20'
                                : 'bg-indigo-500/10 text-indigo-300 border border-indigo-500/20'
                            }`}
                          >
                            {log.action}
                          </span>
                          <span className="font-semibold text-slate-200">
                            {log.target_name}
                          </span>
                        </div>
                        {log.details && (
                          <p className="text-[11px] text-slate-400 mt-0.5">{log.details}</p>
                        )}
                      </div>
                    </div>

                    <div className="flex sm:flex-col items-center sm:items-end justify-between w-full sm:w-auto text-[11px] text-slate-500 gap-1">
                      <span>by <strong className="text-slate-400">{log.actor}</strong></span>
                      <span>{new Date(log.timestamp).toLocaleTimeString()} {new Date(log.timestamp).toLocaleDateString()}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-800 bg-slate-900/50 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-medium text-slate-300 hover:bg-slate-800 transition-colors"
          >
            Close
          </button>
        </div>

      </div>
    </div>
  );
};
