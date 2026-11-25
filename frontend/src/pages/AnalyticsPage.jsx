import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { 
  BarChart3, 
  TrendingUp, 
  CheckCircle2, 
  Clock, 
  AlertTriangle, 
  Users, 
  CheckSquare,
  Activity
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

export default function AnalyticsPage() {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const res = await api.get('/analytics/metrics');
        setMetrics(res.data);
      } catch (err) {
        console.error('Failed to load analytics', err);
      } finally {
        setLoading(false);
      }
    };
    fetchMetrics();
  }, []);

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold text-[#0F172A] tracking-tight flex items-center gap-2.5">
          <BarChart3 className="w-5 h-5 text-[#2563EB]" />
          <span>Analytics & Performance Metrics</span>
        </h2>
        <p className="text-xs text-[#64748B] mt-1">
          Quantitative tracking of meeting task completion rates, priority bottlenecks, and team bandwidth.
        </p>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-5 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm">
          <span className="text-xs font-medium text-[#64748B]">Task Completion Rate</span>
          <p className="text-2xl font-bold text-[#059669] mt-2">{metrics?.completion_rate || 0}%</p>
          <span className="text-[11px] text-[#64748B] mt-1 inline-block">Based on all approved deliverables</span>
        </div>

        <div className="p-5 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm">
          <span className="text-xs font-medium text-[#64748B]">Total Tracked Deliverables</span>
          <p className="text-2xl font-bold text-[#2563EB] mt-2">{metrics?.total_tasks || 0}</p>
          <span className="text-[11px] text-[#64748B] mt-1 inline-block">Active in MongoDB Atlas</span>
        </div>

        <div className="p-5 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm">
          <span className="text-xs font-medium text-[#64748B]">Team Member Availability</span>
          <p className="text-2xl font-bold text-[#7C3AED] mt-2">
            {metrics?.team_metrics?.available_members || 0} / {metrics?.team_metrics?.total_members || 0}
          </p>
          <span className="text-[11px] text-[#059669] font-medium mt-1 inline-block">Ready for task assignments</span>
        </div>
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Status Distribution */}
        <div className="p-6 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm space-y-4">
          <div>
            <h3 className="text-sm font-bold text-[#0F172A]">Deliverables by Lifecycle Status</h3>
            <p className="text-xs text-[#64748B]">Tasks progression across Kanban pipeline</p>
          </div>

          <div className="h-60 w-full pt-2">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={metrics?.status_distribution || []} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <XAxis dataKey="status" stroke="#94A3B8" fontSize={11} tickLine={false} />
                <YAxis stroke="#94A3B8" fontSize={11} tickLine={false} allowDecimals={false} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#FFFFFF', borderColor: '#E2E8F0', borderRadius: '12px', fontSize: '12px' }}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {metrics?.status_distribution?.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Priority Distribution */}
        <div className="p-6 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm space-y-4">
          <div>
            <h3 className="text-sm font-bold text-[#0F172A]">Task Priority Breakdown</h3>
            <p className="text-xs text-[#64748B]">Risk and urgency classification of deliverables</p>
          </div>

          <div className="h-60 w-full pt-2">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={metrics?.priority_distribution || []} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <XAxis dataKey="priority" stroke="#94A3B8" fontSize={11} tickLine={false} />
                <YAxis stroke="#94A3B8" fontSize={11} tickLine={false} allowDecimals={false} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#FFFFFF', borderColor: '#E2E8F0', borderRadius: '12px', fontSize: '12px' }}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {metrics?.priority_distribution?.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}
