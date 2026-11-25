import React, { useState, useEffect } from 'react';
import { 
  Calendar, 
  FileText, 
  Search, 
  Filter, 
  Clock, 
  ChevronRight, 
  Mic, 
  Sparkles,
  Download,
  Users,
  CheckCircle2,
  X,
  Volume2
} from 'lucide-react';
import { Link } from 'react-router-dom';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function MeetingsPage() {
  const { user } = useAuth();
  const isLeader = ['admin', 'team lead', 'team leader', 'team_leader', 'manager', 'team lead / admin', 'team leader / admin'].includes(
    (user?.role || '').toLowerCase()
  );
  const [meetings, setMeetings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedMeeting, setSelectedMeeting] = useState(null);
  const [transcripts, setTranscripts] = useState([]);
  const [meetingTasks, setMeetingTasks] = useState([]);
  const [loadingTranscripts, setLoadingTranscripts] = useState(false);
  const [approvingTaskId, setApprovingTaskId] = useState(null);

  const fetchMeetings = async () => {
    setLoading(true);
    try {
      const res = await api.get('/meetings');
      setMeetings(res.data.meetings || []);
    } catch (err) {
      console.error('Failed to load meetings', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMeetings();
  }, []);

  const handleOpenMeeting = async (meeting) => {
    setSelectedMeeting(meeting);
    setLoadingTranscripts(true);
    try {
      const [trRes, taskRes] = await Promise.all([
        api.get(`/meetings/${meeting.meeting_id}/transcript`),
        api.get(`/meetings/${meeting.meeting_id}/tasks`).catch(() => ({ data: { tasks: [] } }))
      ]);
      setTranscripts(trRes.data || []);
      setMeetingTasks(taskRes.data?.tasks || []);
    } catch (err) {
      console.error('Failed to fetch transcript or tasks', err);
      setTranscripts([]);
      setMeetingTasks([]);
    } finally {
      setLoadingTranscripts(false);
    }
  };

  const handleApproveTaskFromModal = async (task) => {
    setApprovingTaskId(task.task_id);
    try {
      await api.post(`/meetings/${selectedMeeting.meeting_id}/tasks/approve`, {
        task_id: task.task_id,
        priority: task.priority,
        deadline: task.deadline,
        assigned_member_id: task.assigned_member_id,
        assigned_member_name: task.assigned_member_name,
        assigned_member_email: task.assigned_member_email,
        assigned_member_role: task.assigned_member_role
      });
      // Update local task state to approved
      setMeetingTasks((prev) =>
        prev.map((t) => (t.task_id === task.task_id ? { ...t, approval_status: 'Approved' } : t))
      );
    } catch (err) {
      alert('Task approval failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setApprovingTaskId(null);
    }
  };

  const filteredMeetings = meetings.filter((m) => {
    const title = m.meeting_title || m.title || '';
    const summary = m.meeting_summary || m.summary || '';
    const term = searchTerm.toLowerCase();
    return title.toLowerCase().includes(term) || summary.toLowerCase().includes(term);
  });

  const handleDownloadPDF = (meetingId) => {
    window.open(`${api.defaults.baseURL}/meetings/${meetingId}/export-pdf`, '_blank');
  };

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-[#0F172A] tracking-tight flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-[#EFF6FF] text-[#2563EB] flex items-center justify-center">
              <Calendar className="w-5 h-5" />
            </div>
            <span>Meeting History & Transcripts</span>
          </h2>
          <p className="text-xs text-[#64748B] mt-1">
            Archived team recordings, speaker-attributed transcripts, and AI-extracted deliverables stored in MongoDB.
          </p>
        </div>

        <Link
          to="/live-meeting"
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold shadow-sm transition self-start sm:self-auto cursor-pointer"
        >
          <Mic className="w-4 h-4" />
          <span>Start Live Meeting</span>
        </Link>
      </div>

      {/* Filter / Search Bar */}
      <div className="p-4 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm flex flex-wrap items-center justify-between gap-3">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="w-4 h-4 text-[#94A3B8] absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search meetings by title, topic, or summary..."
            className="w-full pl-9 pr-3.5 py-2 text-xs rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-[#0F172A] placeholder-[#94A3B8] focus:outline-none focus:border-[#2563EB] transition"
          />
        </div>
      </div>

      {/* Meetings Grid or Empty State */}
      {loading ? (
        <div className="py-16 text-center text-xs text-[#64748B]">
          <div className="w-6 h-6 border-2 border-[#2563EB] border-t-transparent rounded-full animate-spin mx-auto mb-2" />
          Loading meeting history...
        </div>
      ) : filteredMeetings.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredMeetings.map((meeting) => (
            <div
              key={meeting.meeting_id}
              onClick={() => handleOpenMeeting(meeting)}
              className="p-5 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm hover:border-[#2563EB]/40 hover:shadow-md transition cursor-pointer space-y-3.5 flex flex-col justify-between"
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[10px] text-[#2563EB] font-bold">
                    {meeting.meeting_id}
                  </span>
                  <span className={`text-[10px] px-2 py-0.5 rounded-md font-semibold border ${
                    meeting.status === 'Completed'
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      : 'bg-amber-50 text-amber-700 border-amber-200'
                  }`}>
                    {meeting.status || 'Completed'}
                  </span>
                </div>

                <h3 className="font-bold text-sm text-[#0F172A] line-clamp-1">
                  {meeting.meeting_title || meeting.title}
                </h3>

                <p className="text-xs text-[#64748B] line-clamp-2 leading-relaxed">
                  {meeting.meeting_summary || meeting.summary || 'Click to view full transcript and action items.'}
                </p>
              </div>

              <div className="pt-3 border-t border-[#E2E8F0] flex items-center justify-between text-[11px] text-[#64748B]">
                <div className="flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5" />
                  <span>{meeting.duration || '00:00'}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-[#2563EB]" />
                  <span>{meeting.action_items?.length || 0} Action Items</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="p-16 rounded-2xl bg-white border border-[#E2E8F0] text-center space-y-4 shadow-sm">
          <div className="w-16 h-16 rounded-2xl bg-[#EFF6FF] border border-[#BFDBFE] flex items-center justify-center text-[#2563EB] mx-auto shadow-sm">
            <FileText className="w-8 h-8" />
          </div>
          <div className="space-y-1">
            <h3 className="text-base font-bold text-[#0F172A]">No Recorded Meetings in Archive</h3>
            <p className="text-xs text-[#64748B] max-w-md mx-auto leading-relaxed">
              Record meetings live in the studio or upload audio files. Whisper transcripts, Pyannote speaker labels, and Groq agent recommendations will be archived here in MongoDB Atlas.
            </p>
          </div>
          <div className="pt-2">
            <Link
              to="/live-meeting"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#EFF6FF] border border-[#BFDBFE] hover:bg-[#DBEAFE] text-[#2563EB] text-xs font-semibold transition"
            >
              <Sparkles className="w-4 h-4" />
              <span>Launch Live Studio</span>
            </Link>
          </div>
        </div>
      )}

      {/* Meeting Details Modal */}
      {selectedMeeting && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-2xl w-full max-h-[90vh] overflow-y-auto p-6 space-y-5 border border-[#E2E8F0] shadow-2xl">
            <div className="flex items-center justify-between pb-2 border-b border-[#E2E8F0]">
              <div className="space-y-0.5">
                <span className="font-mono text-xs font-bold text-[#2563EB]">{selectedMeeting.meeting_id}</span>
                <h3 className="text-base font-bold text-[#0F172A]">{selectedMeeting.meeting_title || selectedMeeting.title}</h3>
              </div>
              <button
                onClick={() => setSelectedMeeting(null)}
                className="p-1.5 rounded-lg text-[#64748B] hover:text-[#0F172A] hover:bg-[#F8FAFC] transition cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Audio Player if available */}
            {selectedMeeting.audio_path && (
              <div className="p-3.5 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] space-y-1.5">
                <span className="text-[11px] font-semibold text-[#0F172A] flex items-center gap-1.5">
                  <Volume2 className="w-3.5 h-3.5 text-[#2563EB]" />
                  <span>Recorded Audio Playback</span>
                </span>
                <audio
                  controls
                  src={`${api.defaults.baseURL}/meetings/${selectedMeeting.meeting_id}/audio`}
                  className="w-full h-8"
                />
              </div>
            )}

            {/* Executive Summary */}
            <div className="space-y-2">
              <h4 className="text-xs font-bold text-[#0F172A]">AI Executive Summary (Groq LLaMA 3.3)</h4>
              <p className="text-xs text-[#475569] leading-relaxed p-3.5 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0]">
                {selectedMeeting.meeting_summary || selectedMeeting.summary || 'No summary available.'}
              </p>
            </div>

            {/* Key Decisions */}
            {selectedMeeting.key_decisions?.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-bold text-[#0F172A]">Key Decisions</h4>
                <div className="space-y-1.5">
                  {selectedMeeting.key_decisions.map((dec, idx) => (
                    <div key={idx} className="flex items-center gap-2 text-xs text-[#0F172A]">
                      <CheckCircle2 className="w-3.5 h-3.5 text-[#059669] flex-shrink-0" />
                      <span>{dec}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Extracted Tasks & Human Approval */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-[#0F172A] flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-[#2563EB]" />
                  <span>Extracted Deliverables & Tasks ({meetingTasks.length})</span>
                </h4>
                <span className="text-[10px] text-[#64748B]">Persistent MongoDB Records</span>
              </div>

              {meetingTasks.length > 0 ? (
                <div className="space-y-2 max-h-60 overflow-y-auto">
                  {meetingTasks.map((t) => {
                    const isApproved = t.approval_status === 'Approved';
                    const isPending = !['approved', 'rejected'].includes((t.approval_status || '').toLowerCase());
                    return (
                      <div
                        key={t.task_id}
                        className="p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] space-y-1.5 text-xs"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-bold text-[#0F172A]">{t.title}</span>
                          <span
                            className={`text-[10px] font-bold px-2 py-0.5 rounded-md border ${
                              isApproved
                                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                : 'bg-amber-50 text-amber-700 border-amber-200'
                            }`}
                          >
                            {isApproved ? 'Approved ✓' : t.approval_status || 'Awaiting Approval'}
                          </span>
                        </div>
                        {t.evidence && (
                          <p className="text-[11px] text-[#64748B] italic">"{t.evidence}"</p>
                        )}
                        <div className="flex items-center justify-between text-[11px] text-[#64748B] pt-1">
                          <span>
                            Owner: <strong className="text-[#0F172A]">{t.assigned_member_name || 'Unassigned'}</strong>
                          </span>
                          <span className="text-[#2563EB] font-semibold">{t.priority || 'Medium'}</span>
                        </div>

                        {isPending && isLeader && (
                          <div className="pt-1.5 flex justify-end">
                            <button
                              onClick={() => handleApproveTaskFromModal(t)}
                              disabled={approvingTaskId === t.task_id}
                              className="px-3 py-1 rounded-lg bg-[#059669] hover:bg-[#047857] text-white text-[11px] font-semibold shadow-xs cursor-pointer flex items-center gap-1"
                            >
                              <CheckCircle2 className="w-3 h-3" />
                              <span>{approvingTaskId === t.task_id ? 'Approving...' : 'Approve Task'}</span>
                            </button>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-[#64748B] p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0]">
                  No structured tasks extracted for this meeting.
                </p>
              )}
            </div>

            {/* Transcript Segments */}
            <div className="space-y-2">
              <h4 className="text-xs font-bold text-[#0F172A]">Speaker-Attributed Transcript</h4>
              <div className="max-h-56 overflow-y-auto space-y-2 p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0]">
                {loadingTranscripts ? (
                  <p className="text-xs text-[#64748B]">Loading transcript...</p>
                ) : transcripts.length > 0 ? (
                  transcripts.map((seg, idx) => (
                    <div key={idx} className="text-xs space-y-0.5">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-[#2563EB]">{seg.speaker_label || `Speaker ${seg.speaker_id || 1}`}</span>
                        <span className="text-[10px] text-[#94A3B8] font-mono">{seg.start?.toFixed ? `${seg.start.toFixed(1)}s` : ''}</span>
                      </div>
                      <p className="text-[#0F172A]">{seg.text}</p>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-[#64748B]">No timestamped segments recorded for this session.</p>
                )}
              </div>
            </div>

            {/* Actions */}
            <div className="pt-3 border-t border-[#E2E8F0] flex items-center justify-between">
              <span className="text-[11px] text-[#64748B]">
                Recorded: {new Date(selectedMeeting.created_at).toLocaleDateString()}
              </span>
              <button
                onClick={() => handleDownloadPDF(selectedMeeting.meeting_id)}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold shadow-xs transition cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Export PDF Report</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
