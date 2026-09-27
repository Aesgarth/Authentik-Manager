import React, { useState } from 'react';
import { X, MessageSquare, Check, RefreshCw, Smartphone, LogOut, Send, AlertTriangle } from 'lucide-react';
import { WhatsAppStatus } from '../types';

interface WhatsAppModalProps {
  isOpen: boolean;
  onClose: () => void;
  status: WhatsAppStatus | null;
  onRefresh: () => Promise<void>;
  onLogout: () => Promise<void>;
  onSendMessage: (recipient: string, message: string) => Promise<any>;
}

export const WhatsAppModal: React.FC<WhatsAppModalProps> = ({
  isOpen,
  onClose,
  status,
  onRefresh,
  onLogout,
  onSendMessage,
}) => {
  const [testRecipient, setTestRecipient] = useState('');
  const [testMessage, setTestMessage] = useState('Hello! This is a test message from Authentik Access Manager.');
  const [sending, setSending] = useState(false);
  const [sendSuccess, setSendSuccess] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  if (!isOpen) return null;

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await onRefresh();
    } finally {
      setRefreshing(false);
    }
  };

  const handleSendTest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!testRecipient) return;

    setSending(true);
    setSendSuccess(null);
    setSendError(null);
    try {
      await onSendMessage(testRecipient, testMessage);
      setSendSuccess('Test message sent successfully!');
      setTimeout(() => setSendSuccess(null), 4000);
    } catch (err: any) {
      setSendError(err.message || 'Failed to send test message');
    } finally {
      setSending(false);
    }
  };

  const isConnected = status?.status === 'connected';
  const isQrReady = status?.status === 'qr_ready' && Boolean(status?.qrCodeDataUrl);
  const isOffline = status?.status === 'service_offline';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in">
      <div className="bg-[#111827] border border-[#25354b] rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        
        {/* Header */}
        <div className="p-5 border-b border-[#25354b] bg-[#16202e] flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="h-9 w-9 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 flex items-center justify-center">
              <MessageSquare className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <span>WhatsApp Bridge (Baileys)</span>
                <span
                  className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${
                    isConnected
                      ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                      : isQrReady
                      ? 'bg-amber-500/10 text-amber-400 border-amber-500/30 animate-pulse'
                      : 'bg-[#1e2c3f] text-slate-400 border-[#2c3f58]'
                  }`}
                >
                  {isConnected ? 'Connected' : isQrReady ? 'Scan QR Code' : isOffline ? 'Service Offline' : 'Connecting'}
                </span>
              </h3>
              <p className="text-xs text-slate-400">
                Directly send invitation links to users on WhatsApp.
              </p>
            </div>
          </div>
          <div className="flex items-center space-x-1">
            <button
              onClick={handleRefresh}
              className={`p-1.5 text-slate-400 hover:text-white hover:bg-[#1e2c3f] rounded-lg transition-colors ${
                refreshing ? 'animate-spin text-emerald-400' : ''
              }`}
              title="Refresh status"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
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
          
          {/* Offline Warning */}
          {isOffline && (
            <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-start gap-2.5">
              <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-amber-200">WhatsApp Service Offline</p>
                <p className="text-[11px] text-amber-300/80 mt-1">
                  The Baileys bridge container is not reachable at port 3001. Ensure the container is active.
                </p>
              </div>
            </div>
          )}

          {/* Connected View */}
          {isConnected && (
            <div className="space-y-4">
              <div className="bg-[#0b0f17] border border-emerald-500/30 rounded-xl p-4 flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="h-10 w-10 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center justify-center font-bold">
                    <Smartphone className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-slate-200">Paired WhatsApp Device</p>
                    <p className="text-sm font-mono text-emerald-400 font-bold">
                      +{status?.phone}
                    </p>
                    {status?.lastConnected && (
                      <p className="text-[10px] text-slate-500 mt-0.5">
                        Active since {new Date(status.lastConnected).toLocaleTimeString()}
                      </p>
                    )}
                  </div>
                </div>

                <button
                  onClick={onLogout}
                  className="flex items-center space-x-1.5 bg-[#16202e] hover:bg-rose-950/60 text-slate-300 hover:text-rose-400 text-xs px-3 py-2 rounded-lg border border-[#25354b] hover:border-rose-500/30 transition-colors"
                  title="Unlink and pair a different phone"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  <span>Unlink</span>
                </button>
              </div>

              {/* Test Message Box */}
              <div className="bg-[#0b0f17] border border-[#25354b] rounded-xl p-4 space-y-3">
                <h4 className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
                  <Send className="h-3.5 w-3.5 text-emerald-400" />
                  <span>Send Test Message</span>
                </h4>

                {sendSuccess && (
                  <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs flex items-center gap-1.5">
                    <Check className="h-4 w-4" />
                    <span>{sendSuccess}</span>
                  </div>
                )}
                {sendError && (
                  <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs">
                    {sendError}
                  </div>
                )}

                <form onSubmit={handleSendTest} className="space-y-2.5">
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                      Recipient Mobile Number (e.g. +44 7123 456789 or 07123456789)
                    </label>
                    <input
                      type="text"
                      placeholder="+44 7123 456789"
                      value={testRecipient}
                      onChange={(e) => setTestRecipient(e.target.value)}
                      className="w-full bg-[#111827] border border-[#25354b] rounded-lg px-3 py-1.5 text-xs text-slate-100 placeholder-slate-600 focus:outline-none focus:border-emerald-500 font-mono"
                      required
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                      Message Text
                    </label>
                    <textarea
                      rows={2}
                      value={testMessage}
                      onChange={(e) => setTestMessage(e.target.value)}
                      className="w-full bg-[#111827] border border-[#25354b] rounded-lg p-2 text-xs text-slate-100 placeholder-slate-600 focus:outline-none focus:border-emerald-500"
                      required
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={sending}
                    className="flex items-center justify-center space-x-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-semibold px-4 py-2 rounded-lg transition-colors w-full"
                  >
                    <Send className="h-3.5 w-3.5" />
                    <span>{sending ? 'Sending...' : 'Send Message'}</span>
                  </button>
                </form>
              </div>
            </div>
          )}

          {/* QR Code Scan View */}
          {isQrReady && (
            <div className="text-center space-y-4 py-2">
              <div className="bg-white p-3 rounded-2xl inline-block shadow-xl border border-slate-700">
                <img
                  src={status.qrCodeDataUrl!}
                  alt="WhatsApp QR Code"
                  className="h-56 w-56 object-contain rounded-lg"
                />
              </div>

              <div className="text-left bg-[#0b0f17] border border-[#25354b] rounded-xl p-3.5 space-y-2">
                <h4 className="text-xs font-semibold text-white">How to Pair with Your Phone:</h4>
                <ol className="list-decimal pl-4 space-y-1 text-slate-400 text-[11px]">
                  <li>Open <strong>WhatsApp</strong> on your phone.</li>
                  <li>Tap <strong>Settings</strong> (iPhone) or <strong>Three Dots Menu</strong> (Android).</li>
                  <li>Tap <strong>Linked Devices</strong> &gt; <strong>Link a Device</strong>.</li>
                  <li>Scan the QR code displayed above.</li>
                </ol>
              </div>

              <p className="text-[11px] text-slate-500">
                Authentication tokens are stored locally and encrypted in your persistent volume.
              </p>
            </div>
          )}

          {/* Connecting State */}
          {!isConnected && !isQrReady && !isOffline && (
            <div className="text-center py-10 space-y-3">
              <div className="h-10 w-10 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto" />
              <p className="text-xs text-slate-300">Connecting to WhatsApp socket...</p>
              <p className="text-[11px] text-slate-500">Generating pairing credentials</p>
            </div>
          )}

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
