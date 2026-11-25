import React, { useState } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import { useAuth } from '../context/AuthContext';
import { 
  Mic, 
  Search, 
  Bell, 
  ChevronDown, 
  Database, 
  Users, 
  Sparkles,
  CheckCircle2
} from 'lucide-react';

export default function AppLayout() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [showNotifications, setShowNotifications] = useState(false);

  return (
    <div className="flex min-h-screen bg-[#F8FAFC] text-[#0F172A]">
      {/* Sidebar */}
      <Sidebar />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        {/* Top Header */}
        <header className="h-16 border-b border-[#E2E8F0] bg-white px-8 flex items-center justify-between sticky top-0 z-10 shadow-sm">
          {/* Left: Team Selector & Global Search */}
          <div className="flex items-center gap-4 flex-1 max-w-xl">
            {/* Team Selector Pill */}
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-xs font-medium text-[#0F172A] cursor-pointer hover:bg-[#F1F5F9] transition">
              <Users className="w-3.5 h-3.5 text-[#2563EB]" />
              <span className="text-[#64748B]">Team:</span>
              <span className="font-semibold text-[#0F172A]">{user?.team_name || 'Engineering Squad'}</span>
              <ChevronDown className="w-3 h-3 text-[#94A3B8]" />
            </div>

            {/* Global Search Bar */}
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-[#94A3B8] absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search meetings, tasks, team members..."
                className="w-full pl-9 pr-4 py-1.5 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-xs text-[#0F172A] placeholder-[#94A3B8] focus:outline-none focus:border-[#2563EB] focus:bg-white transition"
              />
            </div>
          </div>

          {/* Right Header Actions */}
          <div className="flex items-center gap-3">
            {/* MongoDB Connection Status Pill */}
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-[#ECFDF5] border border-[#A7F3D0] text-xs text-[#059669] font-medium">
              <span className="w-2 h-2 rounded-full bg-[#059669] animate-ping" />
              <Database className="w-3.5 h-3.5" />
              <span>MongoDB Atlas Connected</span>
            </div>

            {/* Notifications Button */}
            <div className="relative">
              <button
                onClick={() => setShowNotifications(!showNotifications)}
                className="p-2 rounded-xl border border-[#E2E8F0] text-[#64748B] hover:text-[#0F172A] hover:bg-[#F8FAFC] transition cursor-pointer relative"
                title="Notifications"
              >
                <Bell className="w-4 h-4" />
                <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-[#2563EB]" />
              </button>

              {/* Notifications Dropdown */}
              {showNotifications && (
                <div className="absolute right-0 mt-2 w-80 bg-white rounded-2xl border border-[#E2E8F0] shadow-xl p-4 space-y-3 z-50">
                  <div className="flex items-center justify-between pb-2 border-b border-[#E2E8F0]">
                    <span className="text-xs font-bold text-[#0F172A]">Notifications</span>
                    <span className="text-[10px] text-[#2563EB] font-semibold cursor-pointer">Mark all read</span>
                  </div>
                  <div className="space-y-2 text-xs">
                    <div className="p-2.5 rounded-xl bg-[#EFF6FF] border border-[#DBEAFE] space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-[#1E40AF]">Task Approved & Dispatched</span>
                        <span className="text-[9px] text-[#64748B]">Just now</span>
                      </div>
                      <p className="text-[11px] text-[#3B82F6]">Zapier webhook synced Trello card & Gmail alert.</p>
                    </div>
                    <div className="p-2.5 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-[#0F172A]">MongoDB Atlas Indexed</span>
                        <span className="text-[9px] text-[#64748B]">10m ago</span>
                      </div>
                      <p className="text-[11px] text-[#64748B]">Member profiles collection synchronized.</p>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Primary Action Button */}
            <button
              onClick={() => navigate('/live-meeting')}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold shadow-sm transition-all cursor-pointer"
            >
              <Mic className="w-3.5 h-3.5" />
              <span>Start Meeting</span>
            </button>
          </div>
        </header>

        {/* Page Content View */}
        <main className="flex-1 p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
