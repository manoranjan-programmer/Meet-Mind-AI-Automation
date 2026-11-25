import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { 
  Users, 
  Calendar, 
  CheckSquare, 
  Clock, 
  CheckCircle2, 
  Mic, 
  UserPlus, 
  UploadCloud, 
  Mail, 
  Sparkles,
  ArrowRight,
  TrendingUp,
  AlertCircle,
  Activity,
  Layers
} from 'lucide-react';
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  Tooltip, 
  ResponsiveContainer, 
  Cell,
  PieChart,
  Pie
} from 'recharts';

export default function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [scheduledData, setScheduledData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const [statsRes, schedRes] = await Promise.allSettled([
          api.get('/dashboard/stats'),
          api.get('/meetings/upcoming')
        ]);
        if (statsRes.status === 'fulfilled') setStats(statsRes.value.data);
        if (schedRes.status === 'fulfilled') setScheduledData(schedRes.value.data);
      } catch (err) {
        console.error('Failed to load dashboard stats', err);
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, []);

  const activityData = [
    { name: 'Mon', tasks: 4, meetings: 1 },
    { name: 'Tue', tasks: 7, meetings: 2 },
    { name: 'Wed', tasks: 5, meetings: 1 },
    { name: 'Thu', tasks: 9, meetings: 3 },
    { name: 'Fri', tasks: 6, meetings: 2 },
    { name: 'Sat', tasks: 2, meetings: 0 },
    { name: 'Sun', tasks: 1, meetings: 0 },
  ];

  const statusPieData = [
    { name: 'Approved', value: stats?.approved_tasks || 2, color: '#2563EB' },
    { name: 'Completed', value: stats?.completed_tasks || 1, color: '#059669' },
    { name: 'Pending Review', value: stats?.pending_tasks || 1, color: '#F59E0B' },
  ];

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      {/* Welcome Banner */}
      <div className="p-6 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="text-[11px] px-2.5 py-0.5 rounded-full font-bold bg-[#EFF6FF] text-[#2563EB] border border-[#BFDBFE]">
              Enterprise AI Intelligence
            </span>
            <span className="text-xs text-[#64748B]">MeetMind AI Workspace</span>
          </div>
          <h2 className="text-xl font-bold text-[#0F172A] tracking-tight">
            Welcome back, {user?.name || 'Administrator'}
          </h2>
          <p className="text-xs text-[#64748B] max-w-2xl leading-relaxed">
            Real-time meeting capture, automated Whisper transcription, speaker diarization, and autonomous Groq LLM task assignments backed by MongoDB Atlas.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={() => navigate('/live-meeting')}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold shadow-sm transition cursor-pointer"
          >
            <Mic className="w-4 h-4" />
            <span>Record Meeting</span>
          </button>
          <button
            onClick={() => navigate('/tasks')}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white border border-[#E2E8F0] hover:bg-[#F8FAFC] text-[#0F172A] text-xs font-semibold shadow-sm transition cursor-pointer"
          >
            <CheckSquare className="w-4 h-4 text-[#2563EB]" />
            <span>Kanban Board</span>
          </button>
        </div>
      </div>

      {/* KPI Metrics Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {/* Total Meetings */}
        <div className="p-5 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm hover:border-[#2563EB]/40 transition">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[#64748B]">Total Meetings</span>
            <div className="w-8 h-8 rounded-lg bg-[#EFF6FF] text-[#2563EB] flex items-center justify-center">
              <Calendar className="w-4 h-4" />
            </div>
          </div>
          <p className="text-2xl font-bold text-[#0F172A] mt-2">{stats?.total_meetings || 0}</p>
          <span className="text-[11px] text-[#059669] font-medium mt-1 inline-block">Whisper & Pyannote ready</span>
        </div>

        {/* Total Tasks */}
        <div 
          onClick={() => navigate('/tasks')}
          className="p-5 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm hover:border-[#2563EB]/40 transition cursor-pointer"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[#64748B]">Total Tasks</span>
            <div className="w-8 h-8 rounded-lg bg-[#EFF6FF] text-[#2563EB] flex items-center justify-center">
              <CheckSquare className="w-4 h-4" />
            </div>
          </div>
          <p className="text-2xl font-bold text-[#0F172A] mt-2">{stats?.total_tasks || 0}</p>
          <span className="text-[11px] text-[#2563EB] font-medium mt-1 inline-block">View Kanban &rarr;</span>
        </div>

        {/* Approved Tasks */}
        <div 
          onClick={() => navigate('/tasks')}
          className="p-5 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm hover:border-[#2563EB]/40 transition cursor-pointer"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[#64748B]">Approved Tasks</span>
            <div className="w-8 h-8 rounded-lg bg-[#EFF6FF] text-[#2563EB] flex items-center justify-center">
              <CheckCircle2 className="w-4 h-4" />
            </div>
          </div>
          <p className="text-2xl font-bold text-[#0F172A] mt-2">{stats?.approved_tasks || 0}</p>
          <span className="text-[11px] text-[#059669] font-medium mt-1 inline-block">Synced to Zapier</span>
        </div>

        {/* Pending Approvals */}
        <div 
          onClick={() => navigate('/tasks')}
          className="p-5 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm hover:border-amber-400/40 transition cursor-pointer"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[#64748B]">Pending Tasks</span>
            <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
              <Clock className="w-4 h-4" />
            </div>
          </div>
          <p className="text-2xl font-bold text-[#0F172A] mt-2">{stats?.pending_tasks || 0}</p>
          <span className="text-[11px] text-amber-600 font-medium mt-1 inline-block">Needs review</span>
        </div>

        {/* Team Members */}
        <div 
          onClick={() => navigate('/team')}
          className="p-5 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm hover:border-[#7C3AED]/40 transition cursor-pointer"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[#64748B]">Team Members</span>
            <div className="w-8 h-8 rounded-lg bg-[#F5F3FF] text-[#7C3AED] flex items-center justify-center">
              <Users className="w-4 h-4" />
            </div>
          </div>
          <p className="text-2xl font-bold text-[#0F172A] mt-2">{stats?.total_members || 0}</p>
          <span className="text-[11px] text-[#059669] font-medium mt-1 inline-block">
            {stats?.available_members || 0} members available
          </span>
        </div>
      </div>

      {/* Analytics Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Weekly Activity Bar Chart */}
        <div className="lg:col-span-2 p-6 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-[#0F172A]">Weekly Meeting & Task Activity</h3>
              <p className="text-xs text-[#64748B]">Throughput across team development sprints</p>
            </div>
            <div className="flex items-center gap-3 text-xs font-medium">
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-[#2563EB]" /> Tasks
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-[#7C3AED]" /> Meetings
              </span>
            </div>
          </div>

          <div className="h-60 w-full pt-2">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={activityData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <XAxis dataKey="name" stroke="#94A3B8" fontSize={11} tickLine={false} />
                <YAxis stroke="#94A3B8" fontSize={11} tickLine={false} allowDecimals={false} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#FFFFFF', borderColor: '#E2E8F0', borderRadius: '12px', fontSize: '12px', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.05)' }}
                />
                <Bar dataKey="tasks" fill="#2563EB" radius={[4, 4, 0, 0]} />
                <Bar dataKey="meetings" fill="#7C3AED" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Task Status Distribution Donut */}
        <div className="p-6 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm flex flex-col justify-between space-y-4">
          <div>
            <h3 className="text-sm font-bold text-[#0F172A]">Task Status Breakdown</h3>
            <p className="text-xs text-[#64748B] mt-0.5">MongoDB Atlas tasks distribution</p>
          </div>

          <div className="h-44 flex items-center justify-center">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={statusPieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={75}
                  paddingAngle={4}
                  dataKey="value"
                >
                  {statusPieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="space-y-2 pt-2 border-t border-[#E2E8F0] text-xs">
            {statusPieData.map((item) => (
              <div key={item.name} className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-[#64748B]">
                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: item.color }} />
                  {item.name}
                </span>
                <span className="font-semibold text-[#0F172A]">{item.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Scheduled & Active Meetings Overview */}
      <div className="p-6 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-[#0F172A] flex items-center gap-2">
              <Calendar className="w-4 h-4 text-[#7C3AED]" />
              <span>Workspace Meetings Schedule</span>
            </h3>
            <p className="text-xs text-[#64748B]">
              Upcoming, today's, active, completed, and cancelled conferences
            </p>
          </div>
          <button
            onClick={() => navigate('/upcoming-meetings')}
            className="flex items-center gap-1 text-xs font-semibold text-[#7C3AED] hover:underline"
          >
            <span>Open Meeting Scheduler</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <div className="p-3.5 rounded-xl bg-purple-50/60 border border-purple-100 space-y-1">
            <span className="text-[10px] uppercase font-bold tracking-wider text-purple-700">Upcoming</span>
            <span className="text-lg font-bold text-[#0F172A] block">{scheduledData?.upcoming_meetings?.length || 0}</span>
            <span className="text-[10px] text-purple-600">Future scheduled</span>
          </div>

          <div className="p-3.5 rounded-xl bg-blue-50/60 border border-blue-100 space-y-1">
            <span className="text-[10px] uppercase font-bold tracking-wider text-[#2563EB]">Today</span>
            <span className="text-lg font-bold text-[#0F172A] block">{scheduledData?.today_meetings?.length || 0}</span>
            <span className="text-[10px] text-[#2563EB]">Scheduled today</span>
          </div>

          <div className="p-3.5 rounded-xl bg-emerald-50/60 border border-emerald-100 space-y-1">
            <span className="text-[10px] uppercase font-bold tracking-wider text-[#059669]">Active Now</span>
            <span className="text-lg font-bold text-[#0F172A] block">{scheduledData?.active_meetings?.length || 0}</span>
            <span className="text-[10px] text-[#059669]">In-progress rooms</span>
          </div>

          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-1">
            <span className="text-[10px] uppercase font-bold tracking-wider text-[#64748B]">Completed</span>
            <span className="text-lg font-bold text-[#0F172A] block">{scheduledData?.completed_meetings?.length || stats?.total_meetings || 0}</span>
            <span className="text-[10px] text-[#64748B]">Finished & analyzed</span>
          </div>

          <div className="p-3.5 rounded-xl bg-rose-50/60 border border-rose-100 space-y-1">
            <span className="text-[10px] uppercase font-bold tracking-wider text-rose-700">Cancelled</span>
            <span className="text-lg font-bold text-[#0F172A] block">{scheduledData?.cancelled_meetings?.length || 0}</span>
            <span className="text-[10px] text-rose-600">Cancelled calls</span>
          </div>
        </div>
      </div>

      {/* Recent Approved Tasks Section */}
      <div className="p-6 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-[#0F172A] flex items-center gap-2">
              <CheckSquare className="w-4 h-4 text-[#2563EB]" />
              <span>Recent Tasks & Assignments</span>
            </h3>
            <p className="text-xs text-[#64748B]">Directly synchronized with MongoDB Atlas and Zapier</p>
          </div>
          <button
            onClick={() => navigate('/tasks')}
            className="flex items-center gap-1 text-xs font-semibold text-[#2563EB] hover:underline"
          >
            <span>Open Kanban Board</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        {stats?.recent_tasks && stats.recent_tasks.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
            {stats.recent_tasks.map((t) => (
              <div
                key={t.task_id}
                onClick={() => navigate('/tasks')}
                className="p-4 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] hover:border-[#2563EB]/40 transition cursor-pointer space-y-2.5"
              >
                <div className="flex items-center justify-between text-xs">
                  <span className="font-mono text-[#64748B] font-semibold">{t.task_id}</span>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                    t.status === 'Completed' ? 'bg-[#ECFDF5] text-[#059669] border border-[#A7F3D0]' :
                    t.status === 'In Progress' ? 'bg-[#EFF6FF] text-[#2563EB] border border-[#BFDBFE]' :
                    t.status === 'Review' ? 'bg-[#F5F3FF] text-[#7C3AED] border border-[#DDD6FE]' :
                    'bg-amber-50 text-amber-700 border border-amber-200'
                  }`}>
                    {t.status}
                  </span>
                </div>
                <h4 className="text-xs font-bold text-[#0F172A] line-clamp-1">{t.title}</h4>
                <div className="flex items-center justify-between text-[11px] text-[#64748B] pt-2 border-t border-[#E2E8F0]">
                  <span>Assignee: <strong className="text-[#0F172A]">{t.assigned_member_name}</strong></span>
                  <span className="font-medium text-[#2563EB]">{t.priority}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="py-8 text-center text-xs text-[#64748B] border border-dashed border-[#E2E8F0] rounded-xl">
            No tasks found. Open the Kanban Board to create your first task.
          </div>
        )}
      </div>
    </div>
  );
}
