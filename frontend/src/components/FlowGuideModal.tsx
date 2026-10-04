import React, { useState } from 'react';
import { X, Copy, Check, Zap, CheckCircle2, Radio, BellRing, Code, ShieldCheck } from 'lucide-react';
import { api } from '../api/client';

interface FlowGuideModalProps {
  isOpen: boolean;
  onClose: () => void;
  flowGuide: {
    title: string;
    description: string;
    snippet: string;
    webhook_url?: string;
    webhook_snippet?: string;
  } | null;
  onShowToast?: (msg: string, type: 'success' | 'error' | 'info') => void;
}

export const FlowGuideModal: React.FC<FlowGuideModalProps> = ({
  isOpen,
  onClose,
  flowGuide,
  onShowToast,
}) => {
  const [activeTab, setActiveTab] = useState<'webhook' | 'policy' | 'native_transport'>('webhook');
  const [copiedSnippet, setCopiedSnippet] = useState(false);
  const [copiedWebhook, setCopiedWebhook] = useState(false);
  const [copiedUrl, setCopiedUrl] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [installed, setInstalled] = useState(false);

  if (!isOpen || !flowGuide) return null;

  const webhookUrl = flowGuide.webhook_url || `${window.location.origin}/api/webhooks/authentik`;
  const webhookSnippet = flowGuide.webhook_snippet || `# Append to your Guest Write Expression Policy in Authentik:
try:
    import urllib.request, json
    mgr_url = "${webhookUrl}"
    payload = json.dumps({"email": email, "username": email}).encode("utf-8")
    req = urllib.request.Request(mgr_url, data=payload, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=2)
except Exception:
    pass
`;

  const handleCopyPolicy = () => {
    navigator.clipboard.writeText(flowGuide.snippet);
    setCopiedSnippet(true);
    setTimeout(() => setCopiedSnippet(false), 2500);
  };

  const handleCopyWebhookSnippet = () => {
    navigator.clipboard.writeText(webhookSnippet);
    setCopiedWebhook(true);
    setTimeout(() => setCopiedWebhook(false), 2500);
  };

  const handleCopyUrl = () => {
    navigator.clipboard.writeText(webhookUrl);
    setCopiedUrl(true);
    setTimeout(() => setCopiedUrl(false), 2500);
  };

  const handleAutoInstall = async () => {
    try {
      setInstalling(true);
      const res = await api.installFlowPolicy();
      setInstalled(true);
      onShowToast?.(res.message, 'success');
    } catch (err: any) {
      onShowToast?.(err.message || 'Failed to install policy', 'error');
    } finally {
      setInstalling(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in">
      <div className="bg-[#111827] border border-[#25354b] rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        
        {/* Header */}
        <div className="p-5 border-b border-[#25354b] bg-[#16202e] flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="h-9 w-9 rounded-lg bg-orange-500/15 border border-orange-500/30 text-[#fd7e14] flex items-center justify-center">
              <Zap className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Authentik Group Assignment &amp; Webhooks</h3>
              <p className="text-xs text-slate-400">
                Ensure invited users receive their pre-selected application groups during registration.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white hover:bg-[#1e2c3f] rounded-lg transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-[#25354b] bg-[#0d1420] px-5">
          <button
            onClick={() => setActiveTab('webhook')}
            className={`py-3 px-3 text-xs font-semibold border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === 'webhook'
                ? 'border-[#fd7e14] text-[#fd7e14]'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Radio className="h-3.5 w-3.5" />
            <span>Expression Policy Ping (Easiest)</span>
          </button>

          <button
            onClick={() => setActiveTab('native_transport')}
            className={`py-3 px-3 text-xs font-semibold border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === 'native_transport'
                ? 'border-[#fd7e14] text-[#fd7e14]'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <BellRing className="h-3.5 w-3.5" />
            <span>Authentik Webhook Transport</span>
          </button>

          <button
            onClick={() => setActiveTab('policy')}
            className={`py-3 px-3 text-xs font-semibold border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === 'policy'
                ? 'border-[#fd7e14] text-[#fd7e14]'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Code className="h-3.5 w-3.5" />
            <span>Standalone In-Flow Policy</span>
          </button>
        </div>

        {/* Content */}
        <div className="p-5 overflow-y-auto flex-1 space-y-4 text-xs text-slate-300 leading-relaxed">

          {/* TAB 1: EXPRESSION POLICY PING */}
          {activeTab === 'webhook' && (
            <div className="space-y-4">
              <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-3.5 flex items-start gap-3">
                <ShieldCheck className="h-5 w-5 text-emerald-400 shrink-0 mt-0.5" />
                <div className="text-xs text-emerald-200 space-y-1">
                  <div className="font-semibold text-white">Recommended for Preconfigured &amp; OAuth Flows</div>
                  <p className="text-[11px] text-emerald-300/80">
                    If your enrollment flow has a default group configured on the User Write stage (or uses Google OAuth),
                    this non-blocking notification pings Authentik Access Manager to assign the selected app groups
                    via the API right after the user is saved.
                  </p>
                </div>
              </div>

              <div className="bg-[#0b0f17] border border-[#25354b] rounded-xl p-3.5 space-y-2">
                <h4 className="font-semibold text-white text-xs">How to apply:</h4>
                <ol className="list-decimal pl-4 space-y-1.5 text-slate-400 text-[11px]">
                  <li>Open your <strong>Authentik Admin Interface</strong>.</li>
                  <li>Navigate to <strong>Customization &gt; Policies</strong> and edit your existing <strong>Guest Write Expression Policy</strong>.</li>
                  <li>Scroll to the bottom of the expression and append the 5-line notification snippet below.</li>
                  <li>Click <strong>Update</strong>. Authentik will now notify the manager on every user sign-up!</li>
                </ol>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="font-semibold text-white text-xs">Notification Code Snippet:</span>
                  <button
                    onClick={handleCopyWebhookSnippet}
                    className="flex items-center space-x-1.5 bg-[#16202e] hover:bg-[#1e2c3f] text-[#fd7e14] text-xs px-2.5 py-1 rounded-lg border border-[#25354b] transition-colors"
                  >
                    {copiedWebhook ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                    <span>{copiedWebhook ? 'Copied Snippet!' : 'Copy Snippet'}</span>
                  </button>
                </div>
                <pre className="bg-[#0b0f17] border border-[#25354b] rounded-xl p-3.5 font-mono text-[11px] text-slate-300 overflow-x-auto whitespace-pre">
                  {webhookSnippet}
                </pre>
              </div>

              <div className="flex items-center justify-between p-3 rounded-xl bg-[#0b0f17] border border-[#25354b]">
                <div className="text-[11px] text-slate-400">
                  <span className="text-slate-300 font-semibold">Manager Webhook Endpoint:</span>
                  <div className="font-mono text-[#fd7e14] text-xs mt-0.5">{webhookUrl}</div>
                </div>
                <button
                  onClick={handleCopyUrl}
                  className="px-2.5 py-1 bg-[#16202e] hover:bg-[#1e2c3f] text-slate-200 text-xs rounded border border-[#25354b] flex items-center gap-1"
                >
                  {copiedUrl ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                  <span>{copiedUrl ? 'Copied' : 'Copy URL'}</span>
                </button>
              </div>
            </div>
          )}

          {/* TAB 2: AUTHENTIK NATIVE NOTIFICATION TRANSPORT */}
          {activeTab === 'native_transport' && (
            <div className="space-y-4">
              <p>
                You can also configure Authentik's native <strong>Events Notification System</strong> to send webhooks to
                Authentik Access Manager whenever an enrollment event or user registration occurs.
              </p>

              <div className="flex items-center justify-between p-3 rounded-xl bg-[#0b0f17] border border-[#25354b]">
                <div className="text-[11px] text-slate-400">
                  <span className="text-slate-300 font-semibold">Webhook Destination URL:</span>
                  <div className="font-mono text-[#fd7e14] text-xs mt-0.5">{webhookUrl}</div>
                </div>
                <button
                  onClick={handleCopyUrl}
                  className="px-2.5 py-1 bg-[#16202e] hover:bg-[#1e2c3f] text-slate-200 text-xs rounded border border-[#25354b] flex items-center gap-1"
                >
                  {copiedUrl ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                  <span>{copiedUrl ? 'Copied' : 'Copy URL'}</span>
                </button>
              </div>

              <div className="bg-[#0b0f17] border border-[#25354b] rounded-xl p-3.5 space-y-2">
                <h4 className="font-semibold text-white text-xs">Authentik Admin Setup:</h4>
                <ol className="list-decimal pl-4 space-y-1.5 text-slate-400 text-[11px]">
                  <li>Go to <strong>System &gt; Events &gt; Notification Transports</strong> in Authentik.</li>
                  <li>Click <strong>Create</strong> and set:
                    <ul className="list-disc pl-4 mt-1 text-slate-400 space-y-0.5">
                      <li>Name: <code className="text-[#fd7e14]">Authentik Access Manager</code></li>
                      <li>Mode: <code className="text-[#fd7e14]">Webhook (generic)</code></li>
                      <li>Webhook URL: <code className="text-[#fd7e14]">{webhookUrl}</code></li>
                    </ul>
                  </li>
                  <li>Go to <strong>System &gt; Events &gt; Notification Rules</strong>.</li>
                  <li>Click <strong>Create</strong> and select:
                    <ul className="list-disc pl-4 mt-1 text-slate-400 space-y-0.5">
                      <li>Name: <code className="text-[#fd7e14]">Notify Manager on Signups</code></li>
                      <li>Transports: Select <code className="text-[#fd7e14]">Authentik Access Manager</code></li>
                      <li>Severity: <code className="text-[#fd7e14]">Notice</code></li>
                    </ul>
                  </li>
                </ol>
              </div>
            </div>
          )}

          {/* TAB 3: STANDALONE POLICY */}
          {activeTab === 'policy' && (
            <div className="space-y-4">
              <p>{flowGuide.description}</p>

              {/* 1-Click Auto Install Banner */}
              <div className="bg-gradient-to-r from-orange-500/10 via-amber-500/10 to-transparent border border-orange-500/30 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <div className="font-semibold text-white text-xs flex items-center gap-1.5">
                    <Zap className="h-4 w-4 text-[#fd7e14]" />
                    <span>1-Click Automated Setup</span>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    Directly creates the Expression Policy and binds it to your Authentik enrollment flow via API.
                  </p>
                </div>
                <button
                  onClick={handleAutoInstall}
                  disabled={installing || installed}
                  className="px-3.5 py-2 rounded-lg bg-[#fd7e14] hover:bg-[#ea6c0a] disabled:opacity-50 text-white font-semibold text-xs flex items-center justify-center space-x-1.5 transition-all shadow-sm shrink-0"
                >
                  {installed ? (
                    <>
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-300" />
                      <span>Installed &amp; Active</span>
                    </>
                  ) : (
                    <>
                      <Zap className="h-3.5 w-3.5" />
                      <span>{installing ? 'Installing...' : 'Auto-Install to Authentik'}</span>
                    </>
                  )}
                </button>
              </div>

              <div className="bg-[#0b0f17] border border-[#25354b] rounded-xl p-3.5 space-y-2">
                <h4 className="font-semibold text-white text-xs">Manual Policy Setup:</h4>
                <ol className="list-decimal pl-4 space-y-1.5 text-slate-400 text-[11px]">
                  <li>Log in to your <strong>Authentik Admin Interface</strong>.</li>
                  <li>Navigate to <strong>Customization &gt; Policies</strong> and click <strong>Create Policy</strong>.</li>
                  <li>Select <strong>Expression Policy</strong> and give it a name like <code className="text-[#fd7e14]">Assign Invitation Groups</code>.</li>
                  <li>Paste the Python snippet below into the <strong>Expression</strong> box and save.</li>
                  <li>Under <strong>Flows &amp; Stages &gt; Flows</strong>, edit your enrollment flow and bind this policy before user write.</li>
                </ol>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="font-semibold text-white text-xs">Python Expression Policy Code:</span>
                  <button
                    onClick={handleCopyPolicy}
                    className="flex items-center space-x-1.5 bg-[#16202e] hover:bg-[#1e2c3f] text-[#fd7e14] text-xs px-2.5 py-1 rounded-lg border border-[#25354b] transition-colors"
                  >
                    {copiedSnippet ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                    <span>{copiedSnippet ? 'Copied Code!' : 'Copy Code'}</span>
                  </button>
                </div>
                <pre className="bg-[#0b0f17] border border-[#25354b] rounded-xl p-3.5 font-mono text-[11px] text-slate-300 overflow-x-auto whitespace-pre">
                  {flowGuide.snippet}
                </pre>
              </div>
            </div>
          )}

          <p className="text-[11px] text-slate-500 italic">
            * Note: Authentik Access Manager also includes an automated background sync worker that polls Authentik events every 20 seconds.
          </p>
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
