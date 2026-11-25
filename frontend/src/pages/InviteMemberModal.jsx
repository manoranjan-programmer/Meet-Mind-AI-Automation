import React, { useState } from 'react';
import Modal from '../components/Modal';
import api from '../services/api';
import { 
  Send, 
  Copy, 
  Check, 
  Mail, 
  ShieldCheck, 
  AlertCircle,
  CheckCircle2,
  Lock,
  UserCheck
} from 'lucide-react';

export default function InviteMemberModal({ isOpen, onClose, onInvitationCreated }) {
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('Editor'); // 'Editor' | 'Viewer'
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [generatedLink, setGeneratedLink] = useState('');
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const handleSendInvite = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setSuccess('');
    setGeneratedLink('');

    try {
      const res = await api.post('/team/invitations', {
        email: email.trim(),
        role: role,
        message: message.trim() || undefined
      });
      setGeneratedLink(res.data.invitation_url);
      setSuccess(`Invitation successfully created and sent to ${email.trim()}!`);
      if (onInvitationCreated) {
        onInvitationCreated();
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to send invitation.');
    } finally {
      setLoading(false);
    }
  };

  const handleCopyLink = () => {
    if (generatedLink) {
      navigator.clipboard.writeText(generatedLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const resetForm = () => {
    setEmail('');
    setRole('Editor');
    setMessage('');
    setError('');
    setSuccess('');
    setGeneratedLink('');
    setCopied(false);
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={resetForm}
      title="Invite Team Member"
      subtitle="Invite a colleague to join your team with Role-Based Access Control"
      maxWidth="max-w-lg"
    >
      <div className="space-y-4">
        {error && (
          <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {success && (
          <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0 text-emerald-600" />
            <span>{success}</span>
          </div>
        )}

        <form onSubmit={handleSendInvite} className="space-y-4">
          {/* Email Address */}
          <div>
            <label className="block text-xs font-semibold text-[#475569] mb-1.5">
              Email Address *
            </label>
            <div className="relative">
              <Mail className="w-4 h-4 text-[#94A3B8] absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="colleague@example.com"
                className="w-full pl-9 pr-3.5 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:outline-none focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB] transition"
              />
            </div>
            <p className="text-[11px] text-[#64748B] mt-1">
              Must be a valid email. Prevents duplicate pending invitations or existing members.
            </p>
          </div>

          {/* Access Level / Role */}
          <div>
            <label className="block text-xs font-semibold text-[#475569] mb-1.5">
              Access Level (Role) *
            </label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setRole('Editor')}
                className={`p-3 rounded-xl border text-left transition cursor-pointer ${
                  role === 'Editor'
                    ? 'border-[#2563EB] bg-[#EFF6FF] text-[#1E40AF]'
                    : 'border-[#E2E8F0] bg-white text-[#64748B] hover:border-slate-300'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-[#0F172A]">Editor</span>
                  {role === 'Editor' && <Check className="w-4 h-4 text-[#2563EB]" />}
                </div>
                <p className="text-[10px] text-[#64748B] mt-1 leading-snug">
                  Can participate in meetings, create and update tasks, view team resources.
                </p>
              </button>

              <button
                type="button"
                onClick={() => setRole('Viewer')}
                className={`p-3 rounded-xl border text-left transition cursor-pointer ${
                  role === 'Viewer'
                    ? 'border-[#7C3AED] bg-[#F5F3FF] text-[#5B21B6]'
                    : 'border-[#E2E8F0] bg-white text-[#64748B] hover:border-slate-300'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-[#0F172A]">Viewer</span>
                  {role === 'Viewer' && <Check className="w-4 h-4 text-[#7C3AED]" />}
                </div>
                <p className="text-[10px] text-[#64748B] mt-1 leading-snug">
                  Read-only access to dashboard, tasks, meeting summaries. Cannot modify.
                </p>
              </button>
            </div>
          </div>

          {/* Optional Invitation Message */}
          <div>
            <label className="block text-xs font-semibold text-[#475569] mb-1.5">
              Personalized Message (Optional)
            </label>
            <textarea
              rows={2}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Hi, welcome to our MeetMind AI workspace! Let's collaborate..."
              className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:outline-none focus:border-[#2563EB] transition resize-none"
            />
          </div>

          {/* Security Banner */}
          <div className="p-3.5 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-xs text-[#64748B] flex items-start gap-2.5">
            <ShieldCheck className="w-4 h-4 text-[#2563EB] mt-0.5 flex-shrink-0" />
            <div>
              <p className="text-[#0F172A] font-semibold">Single-Use Token & 72-Hour Expiry</p>
              <p className="text-[11px] text-[#64748B] mt-0.5">
                The invitation token is cryptographically hashed and bound to the recipient's email.
                Active membership is only created upon acceptance.
              </p>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold shadow-sm transition disabled:opacity-50 cursor-pointer"
          >
            <Send className="w-4 h-4" />
            <span>{loading ? 'Sending Invitation...' : 'Send Invitation'}</span>
          </button>
        </form>

        {/* Generated Link Box */}
        {generatedLink && (
          <div className="mt-4 p-4 rounded-xl bg-emerald-50 border border-emerald-200 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-emerald-800">
                Invitation Ready & Zapier Webhook Triggered!
              </span>
              <span className="text-[10px] text-[#64748B]">Share with {email}</span>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="text"
                readOnly
                value={generatedLink}
                className="flex-1 px-3 py-2 rounded-lg bg-white border border-emerald-300 text-xs text-[#0F172A] font-mono select-all"
              />
              <button
                type="button"
                onClick={handleCopyLink}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[#059669] hover:bg-[#047857] text-white text-xs font-semibold transition cursor-pointer"
              >
                {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copied ? 'Copied!' : 'Copy'}</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
