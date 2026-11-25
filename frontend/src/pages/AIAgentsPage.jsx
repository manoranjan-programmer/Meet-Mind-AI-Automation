import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { 
  Bot, 
  Cpu, 
  Sparkles, 
  ArrowRight, 
  CheckCircle2, 
  Clock, 
  Radio, 
  Workflow, 
  Database, 
  Zap,
  Mic,
  FileText,
  UserCheck,
  Activity,
  RefreshCw
} from 'lucide-react';

export default function AIAgentsPage() {
  const [agentData, setAgentData] = useState(null);
  const [executions, setExecutions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchStatusAndExecutions = async () => {
    try {
      const [statusRes, execRes] = await Promise.all([
        api.get('/agents/status'),
        api.get('/agents/executions').catch(() => ({ data: { executions: [] } }))
      ]);
      setAgentData(statusRes.data);
      setExecutions(execRes.data?.executions || []);
    } catch (err) {
      console.error('Failed to load agents telemetry', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchStatusAndExecutions();
  }, []);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchStatusAndExecutions();
  };

  const pipelineSteps = [
    { num: 1, name: 'Audio Capture', agent: 'Agent 1', desc: 'MediaRecorder & validation' },
    { num: 2, name: 'Whisper STT', agent: 'Agent 2', desc: 'Speech to timestamps' },
    { num: 3, name: 'Speaker Diarization', agent: 'Agent 3', desc: 'Pyannote voice clustering' },
    { num: 4, name: 'Meeting Analyst', agent: 'Agent 4', desc: 'Groq context & summary' },
    { num: 5, name: 'Task Extraction', agent: 'Agent 5', desc: 'Structured deliverables' },
    { num: 6, name: 'Intelligent Assignment', agent: 'Agent 6', desc: 'Skills & workload match' },
    { num: 7, name: 'Review & Validate', agent: 'Agent 7', desc: 'Human-in-the-loop guard' },
    { num: 8, name: 'Zapier Automation', agent: 'Agent 8', desc: 'Webhook dispatch' },
  ];

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold text-[#0F172A] tracking-tight flex items-center gap-2.5">
              <Bot className="w-5 h-5 text-[#2563EB]" />
              <span>Multi-Agent AI Architecture</span>
            </h2>
            <span className="text-[10px] px-2.5 py-0.5 rounded-full font-bold bg-[#EFF6FF] text-[#2563EB] border border-[#BFDBFE]">
              LangGraph Orchestrated
            </span>
          </div>
          <p className="text-xs text-[#64748B] mt-1">
            8 autonomous specialized agents collaborating in a coordinated workflow pipeline powered by Groq LLM and MongoDB Atlas.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white border border-[#E2E8F0] text-xs font-semibold text-[#0F172A] hover:bg-[#F8FAFC] shadow-xs transition cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-[#2563EB] ${refreshing ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>

          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white border border-[#E2E8F0] text-xs shadow-xs">
            <span className={`w-2 h-2 rounded-full ${agentData?.groq_connected ? 'bg-[#059669]' : 'bg-amber-500'}`} />
            <span className="text-[#64748B]">Groq LLM:</span>
            <span className="font-semibold text-[#0F172A]">
              {agentData?.groq_connected ? 'Online (Llama 3.3)' : 'API Key Ready'}
            </span>
          </div>
        </div>
      </div>

      {/* Visual LangGraph Workflow Pipeline */}
      <div className="p-6 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-[#0F172A] flex items-center gap-2">
              <Workflow className="w-4 h-4 text-[#7C3AED]" />
              <span>LangGraph State Orchestration Diagram</span>
            </h3>
            <p className="text-xs text-[#64748B]">Sequential execution with conditional routing and human approval checkpoint</p>
          </div>
          <span className="text-[10px] text-[#7C3AED] font-bold bg-[#F5F3FF] px-2 py-0.5 rounded border border-[#DDD6FE]">
            START &rarr; 8 Stages &rarr; END
          </span>
        </div>

        {/* Responsive Pipeline Steps */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2.5 pt-2">
          {pipelineSteps.map((step, idx) => (
            <div
              key={step.num}
              className="p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] relative flex flex-col justify-between space-y-2 group hover:border-[#2563EB]/40 transition"
            >
              <div>
                <div className="flex items-center justify-between">
                  <span className="w-5 h-5 rounded-full bg-[#EFF6FF] text-[#2563EB] font-bold text-[10px] flex items-center justify-center">
                    {step.num}
                  </span>
                  <span className="text-[9px] text-[#64748B] font-mono">{step.agent}</span>
                </div>
                <h4 className="text-xs font-bold text-[#0F172A] mt-2 leading-snug">{step.name}</h4>
                <p className="text-[10px] text-[#64748B] mt-0.5 leading-tight">{step.desc}</p>
              </div>

              {idx < pipelineSteps.length - 1 && (
                <div className="hidden lg:block absolute -right-2 top-1/2 -translate-y-1/2 z-10 text-[#CBD5E1]">
                  &rarr;
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Agent Cards Grid */}
      <div className="space-y-4">
        <div>
          <h3 className="text-sm font-bold text-[#0F172A]">Specialized Agent Roster</h3>
          <p className="text-xs text-[#64748B]">Real-time operational status and processing details</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {agentData?.agents?.map((agent) => (
            <div
              key={agent.id}
              className="p-5 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm hover:border-[#2563EB]/40 transition flex flex-col justify-between space-y-3"
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-[#F8FAFC] text-[#64748B] border border-[#E2E8F0]">
                    {agent.role}
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-[#ECFDF5] text-[#059669] border border-[#A7F3D0]">
                    {agent.status}
                  </span>
                </div>

                <h4 className="text-sm font-bold text-[#0F172A]">{agent.name}</h4>
                <p className="text-xs text-[#64748B] leading-relaxed">{agent.purpose}</p>
              </div>

              <div className="pt-3 border-t border-[#E2E8F0] space-y-1.5 text-[11px]">
                <div className="flex items-center justify-between text-[#64748B]">
                  <span>Technology:</span>
                  <span className="font-semibold text-[#0F172A] truncate max-w-[130px]">{agent.tech}</span>
                </div>
                <div className="flex items-center justify-between text-[#64748B]">
                  <span>Processed:</span>
                  <span className="font-semibold text-[#2563EB]">{agent.processed_count} items</span>
                </div>
                <div className="flex items-center justify-between text-[#64748B]">
                  <span>Telemetry:</span>
                  <span className="text-[#059669] font-medium">{agent.last_active}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Live Agent Execution Telemetry Table */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-[#0F172A] flex items-center gap-2">
              <Activity className="w-4 h-4 text-[#2563EB]" />
              <span>Real-Time Execution Logs & Telemetry</span>
            </h3>
            <p className="text-xs text-[#64748B]">Live logs dispatched from LangGraph nodes and MongoDB Atlas persistence</p>
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-[#EFF6FF] text-[#2563EB] border border-[#BFDBFE]">
            {executions.length} Recorded Runs
          </span>
        </div>

        <div className="rounded-2xl bg-white border border-[#E2E8F0] overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#F8FAFC] text-[#64748B] uppercase text-[10px] tracking-wider border-b border-[#E2E8F0]">
                <tr>
                  <th className="px-5 py-3">Agent</th>
                  <th className="px-5 py-3">Meeting / Source</th>
                  <th className="px-5 py-3">Duration</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E2E8F0]">
                {executions.length === 0 ? (
                  <tr>
                    <td colSpan="5" className="px-5 py-8 text-center text-xs text-[#94A3B8]">
                      No agent runs recorded yet. Process or record a meeting to trigger the 8-agent LangGraph pipeline.
                    </td>
                  </tr>
                ) : (
                  executions.map((ex, idx) => (
                    <tr key={idx} className="hover:bg-[#F8FAFC] transition">
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-2">
                          <span className="w-5 h-5 rounded-full bg-[#EFF6FF] text-[#2563EB] text-[10px] font-bold flex items-center justify-center">
                            {ex.agent_id || 'AI'}
                          </span>
                          <span className="font-semibold text-[#0F172A]">{ex.agent_name}</span>
                        </div>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className="font-medium text-[#64748B]">{ex.meeting_title}</span>
                        {ex.meeting_id && (
                          <span className="block text-[10px] text-[#94A3B8] font-mono">{ex.meeting_id}</span>
                        )}
                      </td>
                      <td className="px-5 py-3.5 text-[#64748B] font-mono text-[11px]">
                        {ex.duration ? `${ex.duration.toFixed(2)}s` : '0.12s'}
                      </td>
                      <td className="px-5 py-3.5">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                          ex.status === 'success' || ex.status === 'completed'
                            ? 'bg-[#ECFDF5] text-[#059669] border border-[#A7F3D0]'
                            : ex.status === 'skipped'
                            ? 'bg-amber-50 text-amber-700 border border-amber-200'
                            : 'bg-red-50 text-red-700 border border-red-200'
                        }`}>
                          {ex.status}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 text-[#64748B] text-[11px]">
                        {ex.timestamp ? new Date(ex.timestamp).toLocaleString() : 'Just now'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
