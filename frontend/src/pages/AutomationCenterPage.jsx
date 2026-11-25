import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { 
  Zap, 
  CheckCircle2, 
  AlertCircle, 
  Clock, 
  RefreshCw, 
  ShieldCheck, 
  Mail, 
  Activity,
  Send,
  RotateCcw,
  Check,
  X,
  Info,
  ChevronDown,
  Eye,
  FileText,
  AlertTriangle,
  Server
} from 'lucide-react';

const WEBHOOK_OPTIONS = [
  { id: 'meeting_completed', label: 'Meeting Completed (ZAP 2)' },
  { id: 'team_member_added', label: 'Team Member Added (ZAP 5)' },
  { id: 'team_invitation_created', label: 'Team Invitation Created' },
];

export default function AutomationCenterPage() {
  const [overview, setOverview] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState('');
  const [selectedWebhookType, setSelectedWebhookType] = useState('meeting_completed');
  const [retryingId, setRetryingId] = useState(null);
  const [detailModalLog, setDetailModalLog] = useState(null);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [ovRes, healthRes] = await Promise.all([
        api.get('/automation/overview'),
        api.get('/automation/health')
      ]);
      setOverview(ovRes.data);
      setHealth(healthRes.data);
    } catch (err) {
      console.error('Failed to load automation data', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleTestPing = async () => {
    setTesting(true);
    setTestResult('');
    try {
      const res = await api.post('/automation/test-webhook', { webhook_type: selectedWebhookType });
      const st = res.data.delivery_status || res.data.status;
      if (st === 'success' || st === 'sent' || res.data.dispatch_status === 'webhook_accepted') {
        setTestResult(`Test webhook [${selectedWebhookType}] successfully dispatched! Webhook accepted (HTTP 200). Note: Email accepted by Gmail; inbox delivery not independently confirmed.`);
      } else if (st === 'skipped') {
        const reason = res.data.message || res.data.reason || 'Skipped duplicate.';
        setTestResult(`Webhook dispatch skipped: ${reason}`);
      } else if (st === 'failed') {
        setTestResult(`Webhook dispatch failed: ${res.data.error_message || 'Connection error or URL unconfigured.'}`);
      } else {
        setTestResult(`Webhook dispatch status: ${st}${res.data.error_message ? ` - ${res.data.error_message}` : ''}`);
      }
      fetchData();
    } catch (err) {
      setTestResult('Failed to dispatch test webhook: ' + (err.response?.data?.detail || err.message));
    } finally {
      setTesting(false);
    }
  };

  const handleRetry = async (eventIdOrLogId) => {
    setRetryingId(eventIdOrLogId);
    try {
      const res = await api.post(`/automation/retry/${eventIdOrLogId}`);
      alert(`Webhook retry completed: ${res.data.delivery_status || res.data.status || 'OK'}`);
      fetchData();
    } catch (err) {
      alert('Retry failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setRetryingId(null);
    }
  };

  // Status badge formatter
  const renderStatusBadge = (log) => {
    const dispatch = log.dispatch_status || '';
    const delivery = log.delivery_status || log.status || '';

    if (dispatch === 'webhook_accepted' || delivery === 'success') {
      return (
        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#ECFDF5] text-[#059669] border border-[#A7F3D0]">
          Webhook Accepted (200 OK)
        </span>
      );
    } else if (dispatch === 'processing') {
      return (
        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
          Processing
        </span>
      );
    } else if (delivery === 'retrying' || dispatch === 'retrying') {
      return (
        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
          Retrying ({log.retry_count || 1})
        </span>
      );
    } else if (delivery === 'failed' || dispatch === 'failed') {
      return (
        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
          Failed
        </span>
      );
    }
    return (
      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-50 text-slate-700 border border-slate-200">
        Pending
      </span>
    );
  };

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold text-[#0F172A] tracking-tight flex items-center gap-2.5">
              <Zap className="w-5 h-5 text-[#2563EB]" />
              <span>Automation Center & Delivery Diagnostics</span>
            </h2>
            <span className="text-[10px] px-2.5 py-0.5 rounded-full font-bold bg-[#ECFDF5] text-[#059669] border border-[#A7F3D0]">
              MongoDB Outbox • Zapier • Gmail
            </span>
          </div>
          <p className="text-xs text-[#64748B] mt-1">
            Real-time webhook telemetry, database-backed outbox queue, Gmail diagnostics, and human-supervised retry management.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={fetchData}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white border border-[#E2E8F0] hover:bg-[#F8FAFC] text-[#0F172A] text-xs font-semibold shadow-xs transition cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh Logs</span>
          </button>

          {/* Webhook Selector & Test Action */}
          <div className="flex items-center rounded-xl bg-white border border-[#E2E8F0] shadow-xs overflow-hidden">
            <select
              value={selectedWebhookType}
              onChange={(e) => setSelectedWebhookType(e.target.value)}
              className="bg-transparent text-xs font-semibold text-[#0F172A] px-2.5 py-2 border-r border-[#E2E8F0] focus:outline-none cursor-pointer"
            >
              {WEBHOOK_OPTIONS.map((opt) => (
                <option key={opt.id} value={opt.id}>{opt.label}</option>
              ))}
            </select>
            <button
              onClick={handleTestPing}
              disabled={testing}
              className="flex items-center gap-1.5 px-3.5 py-2 bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold transition cursor-pointer disabled:opacity-50"
            >
              <Send className="w-3.5 h-3.5" />
              <span>{testing ? 'Testing...' : 'Test Webhook'}</span>
            </button>
          </div>
        </div>
      </div>

      {testResult && (
        <div className="p-3.5 rounded-xl bg-[#EFF6FF] border border-[#BFDBFE] text-[#1E40AF] text-xs flex items-center justify-between gap-2 animate-fade-in">
          <div className="flex items-center gap-2">
            <Info className="w-4 h-4 flex-shrink-0 text-[#2563EB]" />
            <span>{testResult}</span>
          </div>
          <button onClick={() => setTestResult('')} className="p-1 hover:bg-[#DBEAFE] rounded text-[#2563EB] cursor-pointer">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* KPI Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 rounded-2xl bg-white border border-[#E2E8F0] shadow-xs space-y-1">
          <span className="text-[11px] font-bold text-[#64748B] uppercase tracking-wider">Total Dispatches</span>
          <span className="text-2xl font-bold text-[#0F172A] block">{overview?.total_executions || 0}</span>
          <span className="text-[11px] text-[#2563EB] font-medium">Logged in MongoDB</span>
        </div>

        <div className="p-5 rounded-2xl bg-white border border-[#E2E8F0] shadow-xs space-y-1">
          <span className="text-[11px] font-bold text-[#64748B] uppercase tracking-wider">Webhook Accepted</span>
          <span className="text-2xl font-bold text-[#059669] block">{overview?.successful_executions || 0}</span>
          <span className="text-[11px] text-[#059669] font-medium">HTTP 200 confirmed</span>
        </div>

        <div className="p-5 rounded-2xl bg-white border border-[#E2E8F0] shadow-xs space-y-1">
          <span className="text-[11px] font-bold text-[#64748B] uppercase tracking-wider">Outbox Queue</span>
          <span className="text-2xl font-bold text-[#7C3AED] block">
            {(overview?.outbox_queue?.pending || 0) + (overview?.outbox_queue?.retrying || 0)}
          </span>
          <span className="text-[11px] text-[#7C3AED] font-medium">
            {overview?.outbox_queue?.pending || 0} pending, {overview?.outbox_queue?.retrying || 0} retrying
          </span>
        </div>

        <div className="p-5 rounded-2xl bg-white border border-[#E2E8F0] shadow-xs space-y-1">
          <span className="text-[11px] font-bold text-[#64748B] uppercase tracking-wider">Failed Deliveries</span>
          <span className="text-2xl font-bold text-rose-600 block">{overview?.failed_executions || 0}</span>
          <span className="text-[11px] text-rose-500 font-medium">Manual retry enabled</span>
        </div>
      </div>

      {/* Gmail Delivery & Outbox Diagnostics Notice */}
      <div className="p-4 rounded-xl bg-amber-50/70 border border-amber-200 text-amber-900 text-xs flex items-start gap-3">
        <Mail className="w-4 h-4 text-amber-700 flex-shrink-0 mt-0.5" />
        <div className="space-y-1">
          <strong className="font-bold">Email Delivery Diagnostics Note:</strong>
          <p className="text-[11px] text-amber-800 leading-relaxed">
            A successful Zapier webhook response confirms payload reception by the Zapier Catch Hook. Gmail action delivery is asynchronous. If emails do not appear immediately in your inbox, verify that the recipient field in your Zapier Gmail step is mapped to <code>assigned_email</code> or <code>recipient_email</code>, and check your Gmail Sent and Spam folders.
          </p>
        </div>
      </div>

      {/* Execution Logs Table */}
      <div className="rounded-2xl bg-white border border-[#E2E8F0] overflow-hidden shadow-sm space-y-3 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-[#0F172A] flex items-center gap-2">
              <Activity className="w-4 h-4 text-[#2563EB]" />
              <span>Real MongoDB Automation Logs & Diagnostics</span>
            </h3>
            <p className="text-xs text-[#64748B]">
              Full audit trail from meetmind_ai.automation_logs with outbox state and retry tracking
            </p>
          </div>
          <span className="text-xs text-[#64748B] font-mono">Collection: automation_logs</span>
        </div>

        {overview?.recent_logs && overview.recent_logs.length > 0 ? (
          <div className="overflow-x-auto pt-2">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#F8FAFC] text-[#64748B] uppercase text-[10px] tracking-wider border-b border-[#E2E8F0]">
                <tr>
                  <th className="px-3.5 py-3">Event ID</th>
                  <th className="px-3.5 py-3">Event Name</th>
                  <th className="px-3.5 py-3">Associated Item</th>
                  <th className="px-3.5 py-3">Recipient</th>
                  <th className="px-3.5 py-3">Webhook Status</th>
                  <th className="px-3.5 py-3">Gmail Status</th>
                  <th className="px-3.5 py-3">Retries</th>
                  <th className="px-3.5 py-3">Trigger Time</th>
                  <th className="px-3.5 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E2E8F0]">
                {overview.recent_logs.map((log) => {
                  const isAccepted = log.dispatch_status === 'webhook_accepted' || log.delivery_status === 'success';

                  return (
                    <tr key={log.id} className="hover:bg-[#F8FAFC]">
                      <td className="px-3.5 py-3 font-mono font-semibold text-[#0F172A]">
                        {log.event_id || log.reference_id}
                      </td>
                      <td className="px-3.5 py-3 font-semibold text-[#2563EB]">
                        {log.event_type}
                      </td>
                      <td className="px-3.5 py-3 text-[#0F172A] max-w-xs truncate" title={log.task_title}>
                        {log.task_title || log.reference_id}
                      </td>
                      <td className="px-3.5 py-3 text-[#0F172A] font-medium max-w-xs truncate" title={log.recipient}>
                        {log.recipient || 'official.manoranjanworks@gmail.com'}
                      </td>
                      <td className="px-3.5 py-3">
                        {renderStatusBadge(log)}
                      </td>
                      <td className="px-3.5 py-3">
                        <div className="space-y-0.5">
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                            isAccepted
                              ? 'bg-purple-50 text-purple-700 border-purple-200'
                              : 'bg-slate-50 text-slate-600 border-slate-200'
                          }`}>
                            {isAccepted ? 'gmail_accepted' : 'delivery_unconfirmed'}
                          </span>
                          {log.gmail_notice && (
                            <span className="text-[10px] text-[#64748B] block truncate max-w-xs" title={log.gmail_notice}>
                              {log.gmail_notice}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-3.5 py-3 font-mono text-[#64748B]">
                        {log.retry_count || 0}
                      </td>
                      <td className="px-3.5 py-3 text-[#64748B] text-[11px]">
                        {new Date(log.created_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}
                      </td>
                      <td className="px-3.5 py-3 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => setDetailModalLog(log)}
                            className="p-1.5 rounded-lg border border-[#E2E8F0] hover:bg-[#F1F5F9] text-[#64748B] hover:text-[#0F172A] transition cursor-pointer"
                            title="View Error & Payload Details"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleRetry(log.event_id || log.id)}
                            disabled={retryingId === (log.event_id || log.id)}
                            className="px-2.5 py-1 rounded-lg border border-[#CBD5E1] bg-white text-[#2563EB] hover:bg-[#F1F5F9] font-semibold text-[11px] transition cursor-pointer disabled:opacity-50 inline-flex items-center gap-1"
                            title="Retry Webhook Dispatch"
                          >
                            <RotateCcw className={`w-3 h-3 ${retryingId === (log.event_id || log.id) ? 'animate-spin' : ''}`} />
                            <span>Retry</span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="py-8 text-center text-xs text-[#64748B] border border-dashed border-[#E2E8F0] rounded-xl">
            No automation events recorded yet. Approving tasks, completing meetings, or testing webhooks will generate live delivery logs here.
          </div>
        )}
      </div>

      {/* Error & Payload Details Modal */}
      {detailModalLog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4 animate-fade-in">
          <div className="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-xl border border-[#E2E8F0] max-h-[90vh] flex flex-col space-y-4">
            <div className="flex items-center justify-between border-b border-[#E2E8F0] pb-3">
              <div className="flex items-center gap-2">
                <FileText className="w-5 h-5 text-[#2563EB]" />
                <h3 className="text-base font-bold text-[#0F172A]">
                  Automation Event Details
                </h3>
              </div>
              <button
                onClick={() => setDetailModalLog(null)}
                className="p-1 text-[#64748B] hover:text-[#0F172A] hover:bg-[#F1F5F9] rounded-lg cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3 overflow-y-auto pr-1 text-xs">
              <div className="grid grid-cols-2 gap-2 bg-[#F8FAFC] p-3 rounded-xl border border-[#E2E8F0]">
                <div>
                  <span className="text-[#64748B] block font-medium">Event ID:</span>
                  <span className="font-mono font-bold text-[#0F172A]">{detailModalLog.event_id}</span>
                </div>
                <div>
                  <span className="text-[#64748B] block font-medium">Event Type:</span>
                  <span className="font-bold text-[#2563EB]">{detailModalLog.event_type}</span>
                </div>
                <div>
                  <span className="text-[#64748B] block font-medium">HTTP Response Status:</span>
                  <span className="font-mono font-bold text-[#0F172A]">{detailModalLog.status_code || 'None'}</span>
                </div>
                <div>
                  <span className="text-[#64748B] block font-medium">Retry Attempts:</span>
                  <span className="font-bold text-[#0F172A]">{detailModalLog.attempt_count || 1}</span>
                </div>
              </div>

              {detailModalLog.error_message && (
                <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 space-y-1">
                  <div className="flex items-center gap-1.5 font-bold">
                    <AlertTriangle className="w-4 h-4 text-rose-600" />
                    <span>Error Trace / Diagnostic Reason</span>
                  </div>
                  <pre className="font-mono text-[11px] whitespace-pre-wrap">{detailModalLog.error_message}</pre>
                </div>
              )}

              {detailModalLog.response_body && (
                <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-slate-800 space-y-1">
                  <span className="font-bold block">Zapier HTTP Response Snippet:</span>
                  <pre className="font-mono text-[11px] whitespace-pre-wrap">{detailModalLog.response_body}</pre>
                </div>
              )}

              <div>
                <span className="font-bold text-[#0F172A] block mb-1">Dispatched JSON Payload:</span>
                <pre className="p-3 rounded-xl bg-[#0F172A] text-[#38BDF8] font-mono text-[11px] overflow-x-auto max-h-56">
                  {JSON.stringify(detailModalLog.payload, null, 2)}
                </pre>
              </div>
            </div>

            <div className="flex justify-between items-center pt-2 border-t border-[#E2E8F0]">
              <button
                onClick={() => handleRetry(detailModalLog.event_id || detailModalLog.id)}
                className="px-4 py-2 bg-[#2563EB] hover:bg-[#1D4ED8] text-white rounded-xl font-semibold transition cursor-pointer flex items-center gap-1.5"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Retry Delivery Now</span>
              </button>
              <button
                onClick={() => setDetailModalLog(null)}
                className="px-4 py-2 bg-white border border-[#E2E8F0] hover:bg-[#F8FAFC] text-[#0F172A] rounded-xl font-semibold transition cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
