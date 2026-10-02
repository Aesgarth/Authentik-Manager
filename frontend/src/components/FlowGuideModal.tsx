import React, { useState } from 'react';
import { X, Copy, Check, Zap, CheckCircle2 } from 'lucide-react';
import { api } from '../api/client';

interface FlowGuideModalProps {
  isOpen: boolean;
  onClose: () => void;
  flowGuide: { title: string; description: string; snippet: string } | null;
  onShowToast?: (msg: string, type: 'success' | 'error' | 'info') => void;
}

export const FlowGuideModal: React.FC<FlowGuideModalProps> = ({
  isOpen,
  onClose,
  flowGuide,
  onShowToast,
}) => {
  const [copied, setCopied] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [installed, setInstalled] = useState(false);

  if (!isOpen || !flowGuide) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(flowGuide.snippet);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
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
              <h3 className="text-base font-bold text-white">{flowGuide.title}</h3>
              <p className="text-xs text-slate-400">
                Configure Authentik to assign checked apps to invited users immediately during signup.
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

        {/* Content */}
        <div className="p-5 overflow-y-auto flex-1 space-y-4 text-xs text-slate-300 leading-relaxed">
          <p>{flowGuide.description}</p>

          {/* 1-Click Auto Install Banner */}
          <div className="bg-gradient-to-r from-orange-500/10 via-amber-500/10 to-transparent border border-orange-500/30 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <div className="font-semibold text-white text-xs flex items-center gap-1.5">
                <Zap className="h-4 w-4 text-[#fd7e14]" />
                <span>1-Click Automated Setup (Recommended)</span>
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
            <h4 className="font-semibold text-white text-xs">Step-by-step Setup in Authentik:</h4>
            <ol className="list-decimal pl-4 space-y-1.5 text-slate-400 text-[11px]">
              <li>Log in to your <strong>Authentik Admin Interface</strong>.</li>
              <li>Navigate to <strong>Customization &gt; Policies</strong> and click <strong>Create Policy</strong>.</li>
              <li>Select <strong>Expression Policy</strong> and give it a name like <code className="text-[#fd7e14]">Assign Invitation Groups</code>.</li>
              <li>Paste the Python snippet below into the <strong>Expression</strong> box and save.</li>
              <li>Navigate to <strong>Flows &amp; Stages &gt; Flows</strong> and edit your enrollment flow (e.g. <code className="text-[#fd7e14]">default-enrollment-flow</code>).</li>
              <li>Under <strong>Stage Bindings</strong>, bind this policy to run <strong>before</strong> the <code className="text-[#fd7e14]">default-user-write</code> stage.</li>
            </ol>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="font-semibold text-white text-xs">Python Expression Policy Code:</span>
              <button
                onClick={handleCopy}
                className="flex items-center space-x-1.5 bg-[#16202e] hover:bg-[#1e2c3f] text-[#fd7e14] text-xs px-2.5 py-1 rounded-lg border border-[#25354b] transition-colors"
              >
                {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                <span>{copied ? 'Copied to Clipboard!' : 'Copy Code'}</span>
              </button>
            </div>
            <pre className="bg-[#0b0f17] border border-[#25354b] rounded-xl p-3.5 font-mono text-[11px] text-slate-300 overflow-x-auto whitespace-pre">
              {flowGuide.snippet}
            </pre>
          </div>

          <p className="text-[11px] text-slate-500 italic">
            * Note: If you do not configure this policy, Authentik Access Manager's built-in background worker will still automatically match and assign permissions via the REST API.
          </p>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-[#25354b] bg-[#16202e] flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-xs font-medium text-slate-300 hover:bg-[#1e2c3f] transition-colors"
          >
            Got it
          </button>
        </div>

      </div>
    </div>
  );
};
