import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Building2, 
  Users, 
  MessageSquare, 
  Calendar, 
  CheckSquare, 
  ShieldCheck, 
  Plus, 
  ArrowRight, 
  UserPlus,
  Radio,
  Clock,
  Sparkles,
  Info
} from 'lucide-react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import InviteMemberModal from './InviteMemberModal';

export default function TeamWorkspacePage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const teamId = user?.team_id || 'team_default';

  const [members, setMembers] = useState([]);
  const [tasksCount, setTasksCount] = useState(0);
  const [upcomingCount, setUpcomingCount] = useState(0);
  const [unreadChatCount, setUnreadChatCount] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [showInviteModal, setShowInviteModal] = useState(false);

  useEffect(() => {
    fetchWorkspaceOverview();
  }, [teamId]);

  const fetchWorkspaceOverview = async () => {
    setIsLoading(true);
    try {
      const [membersRes, tasksRes, unreadRes, schedRes] = await Promise.allSettled([
        api.get(`/team/members`),
        api.get(`/tasks?team_id=${teamId}`),
        api.get(`/workspaces/${teamId}/chat/unread-count`),
        api.get(`/meetings/upcoming?team_id=${teamId}`)
      ]);

      if (membersRes.status === 'fulfilled') {
        setMembers(membersRes.value.data?.members || []);
      }
      if (tasksRes.status === 'fulfilled') {
        setTasksCount(tasksRes.value.data?.total || tasksRes.value.data?.tasks?.length || 0);
      }
      if (unreadRes.status === 'fulfilled') {
        setUnreadChatCount(unreadRes.value.data?.unread_count || 0);
      }
      if (schedRes.status === 'fulfilled') {
        setUpcomingCount(schedRes.value.data?.total || schedRes.value.data?.meetings?.length || 0);
      }
    } catch (err) {
      console.error('Failed to load workspace overview:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const isLeader = user?.role === 'Team Leader' || user?.role === 'Admin' || user?.role === 'Team Lead';

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {/* Workspace Banner */}
      <div className="p-6 rounded-2xl bg-gradient-to-r from-[#1E3A8A] via-[#2563EB] to-[#7C3AED] text-white shadow-md relative overflow-hidden">
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-white/20 backdrop-blur-md border border-white/30 uppercase tracking-wider">
                Workspace Hub
              </span>
              <span className="text-xs text-white/80 font-mono">ID: {teamId}</span>
            </div>
            <h2 className="text-2xl font-bold tracking-tight">
              {user?.team_name || 'MeetMind Enterprise Workspace'}
            </h2>
            <p className="text-xs text-white/80 max-w-xl">
              Centralized collaboration hub for real-time team chat, scheduled conferences, automated task assignment, and role permissions.
            </p>
          </div>

          <div className="flex items-center gap-2">
            {isLeader && (
              <button
                onClick={() => setShowInviteModal(true)}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white text-[#1E3A8A] hover:bg-[#F8FAFC] text-xs font-bold shadow-md transition cursor-pointer"
              >
                <UserPlus className="w-3.5 h-3.5 text-[#2563EB]" />
                <span>Invite Teammate</span>
              </button>
            )}

            <button
              onClick={() => navigate('/live-meeting')}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-bold shadow-md transition cursor-pointer"
            >
              <Radio className="w-3.5 h-3.5 animate-pulse" />
              <span>Launch Studio</span>
            </button>
          </div>
        </div>
      </div>

      {/* Quick Action Navigation Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        
        {/* Card 1: Workspace Chat */}
        <div
          onClick={() => navigate('/chat')}
          className="p-5 rounded-2xl bg-white border border-[#E2E8F0] shadow-xs hover:border-[#2563EB] hover:shadow-md transition cursor-pointer flex flex-col justify-between group"
        >
          <div className="space-y-2">
            <div className="w-10 h-10 rounded-xl bg-[#EFF6FF] text-[#2563EB] flex items-center justify-center group-hover:scale-105 transition-transform">
              <MessageSquare className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-bold text-[#0F172A] group-hover:text-[#2563EB] transition-colors">
              Workspace Chat
            </h3>
            <p className="text-xs text-[#64748B]">
              Private team group messaging with WhatsApp-style presence, emojis, and history.
            </p>
          </div>
          <div className="pt-4 flex items-center justify-between text-xs font-semibold text-[#2563EB]">
            <span>{unreadChatCount > 0 ? `${unreadChatCount} unread` : 'Open Conversation'}</span>
            <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
          </div>
        </div>

        {/* Card 2: Upcoming Meetings */}
        <div
          onClick={() => navigate('/upcoming-meetings')}
          className="p-5 rounded-2xl bg-white border border-[#E2E8F0] shadow-xs hover:border-[#2563EB] hover:shadow-md transition cursor-pointer flex flex-col justify-between group"
        >
          <div className="space-y-2">
            <div className="w-10 h-10 rounded-xl bg-purple-50 text-[#7C3AED] flex items-center justify-center group-hover:scale-105 transition-transform">
              <Calendar className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-bold text-[#0F172A] group-hover:text-[#7C3AED] transition-colors">
              Scheduled Meetings
            </h3>
            <p className="text-xs text-[#64748B]">
              Natural language AI scheduler, meeting countdowns, and instant room entry.
            </p>
          </div>
          <div className="pt-4 flex items-center justify-between text-xs font-semibold text-[#7C3AED]">
            <span>{upcomingCount} Scheduled</span>
            <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
          </div>
        </div>

        {/* Card 3: Task Management */}
        <div
          onClick={() => navigate('/tasks')}
          className="p-5 rounded-2xl bg-white border border-[#E2E8F0] shadow-xs hover:border-[#059669] hover:shadow-md transition cursor-pointer flex flex-col justify-between group"
        >
          <div className="space-y-2">
            <div className="w-10 h-10 rounded-xl bg-emerald-50 text-[#059669] flex items-center justify-center group-hover:scale-105 transition-transform">
              <CheckSquare className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-bold text-[#0F172A] group-hover:text-[#059669] transition-colors">
              Task Management
            </h3>
            <p className="text-xs text-[#64748B]">
              Kanban boards with approved deliverables, deadlines, and Zapier triggers.
            </p>
          </div>
          <div className="pt-4 flex items-center justify-between text-xs font-semibold text-[#059669]">
            <span>{tasksCount} Active Tasks</span>
            <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
          </div>
        </div>

        {/* Card 4: Team Roles & Members */}
        <div
          onClick={() => navigate('/team')}
          className="p-5 rounded-2xl bg-white border border-[#E2E8F0] shadow-xs hover:border-[#2563EB] hover:shadow-md transition cursor-pointer flex flex-col justify-between group"
        >
          <div className="space-y-2">
            <div className="w-10 h-10 rounded-xl bg-[#EFF6FF] text-[#2563EB] flex items-center justify-center group-hover:scale-105 transition-transform">
              <Users className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-bold text-[#0F172A] group-hover:text-[#2563EB] transition-colors">
              Team Members
            </h3>
            <p className="text-xs text-[#64748B]">
              Role-based access management (Team Leader, Editor, Viewer) and invitations.
            </p>
          </div>
          <div className="pt-4 flex items-center justify-between text-xs font-semibold text-[#2563EB]">
            <span>{members.length} Active Members</span>
            <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
          </div>
        </div>

      </div>

      {/* Role Permissions Matrix Card */}
      <div className="p-6 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm space-y-4">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-[#2563EB]" />
          <h3 className="text-sm font-bold text-[#0F172A]">Workspace Role-Based Access Control (RBAC)</h3>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="p-4 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] space-y-2">
            <span className="text-xs font-bold text-[#2563EB] block">Team Leader</span>
            <p className="text-[11px] text-[#64748B]">
              Full workspace authority. Schedule meetings, invite teammates, approve AI deliverables, assign tasks, delete messages, and dispatch automations.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] space-y-2">
            <span className="text-xs font-bold text-[#7C3AED] block">Editor</span>
            <p className="text-[11px] text-[#64748B]">
              Collaborative access. Send and edit messages in workspace chat, attend authorized meetings, view permitted deliverables, and update tasks.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] space-y-2">
            <span className="text-xs font-bold text-[#64748B] block">Viewer</span>
            <p className="text-[11px] text-[#64748B]">
              Read-only visibility. Read workspace chat, attend authorized conferences, view summaries and action items. Cannot approve or edit tasks.
            </p>
          </div>
        </div>
      </div>

      {/* Invite Member Modal */}
      {showInviteModal && (
        <InviteMemberModal
          isOpen={showInviteModal}
          onClose={() => setShowInviteModal(false)}
          onSuccess={fetchWorkspaceOverview}
        />
      )}
    </div>
  );
}
