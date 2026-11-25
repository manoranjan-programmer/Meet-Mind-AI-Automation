import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { 
  LayoutDashboard, 
  Building2,
  MessageSquare,
  Users, 
  Mic, 
  CalendarClock,
  Calendar, 
  CheckSquare, 
  Zap,
  Bot,
  BarChart3,
  Settings, 
  LogOut, 
  Sparkles,
  ChevronRight
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const navItems = [
  { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
  { name: 'Team Workspace', path: '/workspace', icon: Building2 },
  { name: 'Workspace Chat', path: '/chat', icon: MessageSquare },
  { name: 'Team Management', path: '/team', icon: Users },
  { name: 'Live Meeting', path: '/live-meeting', icon: Mic },
  { name: 'Upcoming Meetings', path: '/upcoming-meetings', icon: CalendarClock },
  { name: 'Meeting History', path: '/meetings', icon: Calendar },
  { name: 'Task Management', path: '/tasks', icon: CheckSquare },
  { name: 'Automation Center', path: '/automation', icon: Zap },
  { name: 'AI Agents', path: '/agents', icon: Bot },
  { name: 'Analytics', path: '/analytics', icon: BarChart3 },
  { name: 'Settings', path: '/settings', icon: Settings },
];

export default function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <aside className="w-64 bg-white border-r border-[#E2E8F0] flex flex-col h-screen sticky top-0 select-none z-20 shadow-sm">
      {/* Brand Header */}
      <div className="p-5 border-b border-[#E2E8F0] flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-[#2563EB] to-[#7C3AED] flex items-center justify-center shadow-sm text-white">
          <Bot className="w-5 h-5" />
        </div>
        <div>
          <div className="flex items-center gap-1.5">
            <h1 className="font-bold text-base text-[#0F172A] tracking-tight">MeetMind</h1>
            <span className="text-[10px] px-1.5 py-0.5 rounded font-bold bg-[#EFF6FF] text-[#2563EB] border border-[#BFDBFE]">
              AI
            </span>
          </div>
          <p className="text-[11px] text-[#64748B]">Enterprise Meeting Intelligence</p>
        </div>
      </div>

      {/* Nav Links */}
      <div className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        <div className="px-3 pb-2 text-[10px] uppercase font-bold tracking-wider text-[#94A3B8]">
          Main Menu
        </div>
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-[#EFF6FF] text-[#2563EB] font-semibold border border-[#DBEAFE]'
                    : 'text-[#64748B] hover:text-[#0F172A] hover:bg-[#F8FAFC]'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <div className="flex items-center gap-3">
                    <Icon className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-[#2563EB]' : 'text-[#64748B]'}`} />
                    <span>{item.name}</span>
                  </div>
                  {isActive && <ChevronRight className="w-3.5 h-3.5 text-[#2563EB]" />}
                </>
              )}
            </NavLink>
          );
        })}
      </div>

      {/* AI Agents Pill */}
      <div className="px-4 py-3 mx-3 mb-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-[#059669] animate-pulse" />
          <div className="text-[11px]">
            <span className="font-semibold text-[#0F172A] block">8 Agents Active</span>
            <span className="text-[10px] text-[#64748B]">LangGraph Engine</span>
          </div>
        </div>
        <span className="text-[10px] font-bold text-[#7C3AED] bg-[#F5F3FF] px-1.5 py-0.5 rounded border border-[#DDD6FE]">
          Groq LLM
        </span>
      </div>

      {/* User Footer */}
      <div className="p-3 border-t border-[#E2E8F0] bg-white">
        <div className="flex items-center justify-between p-2 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0]">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-[#2563EB] to-[#7C3AED] text-white flex items-center justify-center font-bold text-xs uppercase flex-shrink-0">
              {user?.name ? user.name.slice(0, 2) : 'MM'}
            </div>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-[#0F172A] truncate">{user?.name || 'Administrator'}</p>
              <p className="text-[10px] text-[#64748B] truncate">{user?.role || 'Team Lead'}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            title="Log out"
            className="p-1.5 text-[#64748B] hover:text-red-600 hover:bg-red-50 rounded-lg transition cursor-pointer"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}
