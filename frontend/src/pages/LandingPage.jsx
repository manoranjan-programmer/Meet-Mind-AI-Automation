import React from 'react';
import { Link } from 'react-router-dom';
import { 
  Bot, 
  Mic, 
  Cpu, 
  CheckSquare, 
  Users, 
  Sparkles, 
  ArrowRight, 
  ShieldCheck, 
  Share2,
  CheckCircle2,
  Zap,
  BarChart3,
  Layers
} from 'lucide-react';

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#F8FAFC] text-[#0F172A] flex flex-col selection:bg-[#2563EB] selection:text-white font-sans">
      {/* Top Navbar */}
      <nav className="h-20 bg-white border-b border-[#E2E8F0] px-8 max-w-7xl mx-auto w-full flex items-center justify-between sticky top-0 z-40">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-[#2563EB] to-[#7C3AED] flex items-center justify-center shadow-md shadow-[#2563EB]/20 text-white">
            <Bot className="w-6 h-6" />
          </div>
          <div className="flex flex-col">
            <span className="font-bold text-lg text-[#0F172A] tracking-tight">MeetMind AI</span>
            <span className="text-[10px] text-[#64748B] font-medium tracking-wide uppercase">Meeting Intelligence</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Link
            to="/login"
            className="px-4 py-2 rounded-xl text-xs font-semibold text-[#64748B] hover:text-[#0F172A] hover:bg-[#F8FAFC] transition"
          >
            Sign In
          </Link>
          <Link
            to="/register"
            className="px-5 py-2.5 rounded-xl bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold shadow-sm transition"
          >
            Get Started Free
          </Link>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="flex-1 max-w-5xl mx-auto px-6 py-20 text-center flex flex-col items-center justify-center space-y-6">
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white border border-[#E2E8F0] text-xs shadow-sm">
          <Sparkles className="w-3.5 h-3.5 text-[#2563EB]" />
          <span className="text-[#64748B] font-medium">Autonomous Task Assignment System</span>
          <span className="w-1 h-1 rounded-full bg-[#E2E8F0]" />
          <span className="text-[#7C3AED] font-semibold">8 Agent Architecture</span>
        </div>

        <h1 className="text-4xl sm:text-6xl font-extrabold text-[#0F172A] tracking-tight leading-[1.15] max-w-4xl">
          Turn Team Conversations into <br />
          <span className="bg-gradient-to-r from-[#2563EB] via-[#7C3AED] to-[#059669] bg-clip-text text-transparent">
            Autonomously Assigned Tasks
          </span>
        </h1>

        <p className="text-base text-[#64748B] max-w-2xl leading-relaxed">
          MeetMind AI captures team discussions, transcribes audio with Whisper, identifies speakers, extracts actionable deliverables with Groq, and matches them to team members based on skills, roles, and real-time workload.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-3 pt-4">
          <Link
            to="/register"
            className="flex items-center gap-2 px-6 py-3.5 rounded-xl bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-sm font-semibold shadow-md shadow-[#2563EB]/25 transition cursor-pointer"
          >
            <span>Create Team Workspace</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
          <Link
            to="/login"
            className="flex items-center gap-2 px-6 py-3.5 rounded-xl bg-white border border-[#E2E8F0] hover:bg-[#F8FAFC] text-[#0F172A] text-sm font-semibold shadow-sm transition"
          >
            <span>Demo Sign In</span>
          </Link>
        </div>

        {/* Feature Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-16 text-left w-full">
          <div className="p-6 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm space-y-3 hover:shadow-md transition">
            <div className="w-10 h-10 rounded-xl bg-[#EFF6FF] text-[#2563EB] flex items-center justify-center font-bold">
              <Users className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-[#0F172A]">3 Team Onboarding Methods</h3>
            <p className="text-xs text-[#64748B] leading-relaxed">
              Add members manually with skill tagging, import bulk profiles from CSV/Excel, or invite collaborators with secure self-registration tokens.
            </p>
          </div>

          <div className="p-6 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm space-y-3 hover:shadow-md transition">
            <div className="w-10 h-10 rounded-xl bg-[#F5F3FF] text-[#7C3AED] flex items-center justify-center font-bold">
              <Cpu className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-[#0F172A]">Groq & LangGraph Agents</h3>
            <p className="text-xs text-[#64748B] leading-relaxed">
              An 8-agent pipeline extracts tasks, verifies speaker ownership, analyzes technical requirements, and evaluates capacity.
            </p>
          </div>

          <div className="p-6 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm space-y-3 hover:shadow-md transition">
            <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center font-bold">
              <Share2 className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-[#0F172A]">Zapier Multi-Platform Sync</h3>
            <p className="text-xs text-[#64748B] leading-relaxed">
              One-click task approval automatically dispatches webhooks to send Gmail notifications, create Trello cards, and update Google Sheets.
            </p>
          </div>
        </div>

        {/* 8 Agents Strip */}
        <div className="p-6 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm w-full text-left space-y-3 mt-6">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-[#0F172A] uppercase tracking-wider">Multi-Agent Intelligence Network</span>
            <span className="text-xs text-[#2563EB] font-semibold">8 Autonomous Specialized Agents</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div className="p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-[#0F172A] font-medium">1. Transcription Agent</div>
            <div className="p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-[#0F172A] font-medium">2. Diarization Agent</div>
            <div className="p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-[#0F172A] font-medium">3. Task Extraction Agent</div>
            <div className="p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-[#0F172A] font-medium">4. Ownership Agent</div>
            <div className="p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-[#0F172A] font-medium">5. Skill Matching Agent</div>
            <div className="p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-[#0F172A] font-medium">6. Workload Balancer</div>
            <div className="p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-[#0F172A] font-medium">7. Assignment Optimizer</div>
            <div className="p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-[#0F172A] font-medium">8. Automation Agent</div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="h-16 border-t border-[#E2E8F0] bg-white px-8 max-w-7xl mx-auto w-full flex items-center justify-between text-xs text-[#64748B]">
        <span>© 2026 MeetMind AI. Autonomous Meeting & Task Intelligence.</span>
        <span>Built with React + FastAPI + MongoDB Atlas + Groq + Zapier</span>
      </footer>
    </div>
  );
}
