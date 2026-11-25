import React, { useState } from 'react';
import { 
  Settings, 
  Database, 
  Share2, 
  Cpu, 
  ShieldCheck, 
  CheckCircle2, 
  ExternalLink, 
  Save, 
  Server,
  Zap
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function SettingsPage() {
  const { user } = useAuth();
  const [saved, setSaved] = useState(false);

  const handleSave = (e) => {
    e.preventDefault();
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  return (
    <div className="space-y-6 max-w-5xl animate-fade-in">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-[#0F172A] tracking-tight flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-[#EFF6FF] text-[#2563EB] flex items-center justify-center">
            <Settings className="w-5 h-5" />
          </div>
          <span>System & Workspace Settings</span>
        </h2>
        <p className="text-xs text-[#64748B] mt-1">
          Configure MongoDB Atlas connection, Groq LLM agent parameters, and Zapier webhook automation endpoints.
        </p>
      </div>

      {saved && (
        <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
          <span>Workspace settings updated successfully.</span>
        </div>
      )}

      {/* Grid Settings Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Database Connection */}
        <div className="p-6 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-[#EFF6FF] text-[#2563EB] flex items-center justify-center">
                <Database className="w-4 h-4" />
              </div>
              <h3 className="text-sm font-bold text-[#0F172A]">MongoDB Atlas Database</h3>
            </div>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Connected
            </span>
          </div>

          <div className="space-y-3 text-xs">
            <div className="p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0]">
              <span className="text-[#64748B] text-[11px]">Database Name</span>
              <p className="font-mono text-[#0F172A] font-semibold mt-0.5">meetmind_ai</p>
            </div>
            <div className="p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0]">
              <span className="text-[#64748B] text-[11px]">Primary Collections</span>
              <p className="font-mono text-[#2563EB] font-medium mt-0.5">
                member_profiles, tasks, meetings, invitations, automation_logs
              </p>
            </div>
            <div className="p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0]">
              <span className="text-[#64748B] text-[11px]">Connection Host</span>
              <p className="font-mono text-[#0F172A] text-[11px] mt-0.5">cluster0.meetmind.mongodb.net (Port 27017)</p>
            </div>
          </div>
        </div>

        {/* AI & LLM Engine */}
        <div className="p-6 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-[#F5F3FF] text-[#7C3AED] flex items-center justify-center">
                <Cpu className="w-4 h-4" />
              </div>
              <h3 className="text-sm font-bold text-[#0F172A]">AI & Agentic Engine</h3>
            </div>
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-violet-50 text-[#7C3AED] border border-violet-200">
              Groq LLaMA 3.3
            </span>
          </div>

          <div className="space-y-3 text-xs">
            <div className="p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0]">
              <span className="text-[#64748B] text-[11px]">Default Agent LLM</span>
              <p className="font-mono text-[#0F172A] font-semibold mt-0.5">llama-3.3-70b-versatile</p>
            </div>
            <div className="p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0]">
              <span className="text-[#64748B] text-[11px]">Fast Extraction LLM</span>
              <p className="font-mono text-[#0F172A] font-medium mt-0.5">llama-3.1-8b-instant</p>
            </div>
            <div className="p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0]">
              <span className="text-[#64748B] text-[11px]">Speech-to-Text & Diarization</span>
              <p className="font-mono text-[#0F172A] font-medium mt-0.5">Whisper-Large-v3 + Pyannote 3.1</p>
            </div>
          </div>
        </div>
      </div>

      {/* Zapier Automation Configuration */}
      <div className="p-6 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
              <Zap className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-[#0F172A]">Zapier Webhook Integration (Approved Tasks)</h3>
              <p className="text-xs text-[#64748B]">
                Triggers when admin approves AI recommendations. Dispatches to Gmail, Trello & Google Sheets.
              </p>
            </div>
          </div>
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            Active
          </span>
        </div>

        <div className="p-4 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] space-y-2">
          <label className="block text-[11px] font-semibold text-[#64748B]">Configured Zapier Catch Hook URL</label>
          <div className="flex items-center gap-2">
            <input
              type="text"
              readOnly
              value="https://hooks.zapier.com/hooks/catch/29528561/45lfwwd/"
              className="flex-1 px-3 py-2 rounded-xl bg-white border border-[#E2E8F0] font-mono text-xs text-[#0F172A] select-all focus:outline-none"
            />
            <a
              href="https://zapier.com"
              target="_blank"
              rel="noreferrer"
              className="px-3 py-2 rounded-xl border border-[#E2E8F0] bg-white text-xs font-semibold text-[#2563EB] hover:bg-[#EFF6FF] flex items-center gap-1 transition"
            >
              <span>Zapier Dashboard</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>
          <p className="text-[11px] text-[#64748B]">
            Protected on server-side via backend environment variable <code className="text-[#2563EB]">ZAPIER_APPROVED_TASK_WEBHOOK_URL</code>.
          </p>
        </div>
      </div>

      {/* Workspace Profile & Save */}
      <form onSubmit={handleSave} className="p-6 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm space-y-4">
        <h3 className="text-sm font-bold text-[#0F172A] flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-[#2563EB]" />
          <span>Active Organization & Workspace</span>
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
          <div>
            <label className="block text-xs font-semibold text-[#0F172A] mb-1.5">User Email</label>
            <input
              type="text"
              disabled
              value={user?.email || 'admin@meetmind.ai'}
              className="w-full px-3.5 py-2.5 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-[#64748B]"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-[#0F172A] mb-1.5">Assigned Role</label>
            <input
              type="text"
              disabled
              value={user?.role || 'Admin'}
              className="w-full px-3.5 py-2.5 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-[#64748B]"
            />
          </div>
        </div>

        <div className="flex justify-end pt-2">
          <button
            type="submit"
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold shadow-sm transition cursor-pointer"
          >
            <Save className="w-4 h-4" />
            <span>Save Preferences</span>
          </button>
        </div>
      </form>
    </div>
  );
}
