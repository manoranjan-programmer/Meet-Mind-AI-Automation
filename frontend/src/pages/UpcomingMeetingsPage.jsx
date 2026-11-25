import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  CalendarClock, 
  Sparkles, 
  Calendar, 
  Clock, 
  Users, 
  Radio, 
  Check, 
  X, 
  ArrowRight, 
  AlertCircle, 
  CheckCircle2, 
  HelpCircle,
  Play,
  RotateCcw
} from 'lucide-react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function UpcomingMeetingsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const teamId = user?.team_id || 'team_default';
  const isLeader = ['admin', 'team lead', 'team leader', 'team_leader', 'manager', 'team lead / admin', 'team leader / admin'].includes(
    (user?.role || '').toLowerCase()
  );

  // Natural Language Command State
  const [commandInput, setCommandInput] = useState('');
  const [isParsing, setIsParsing] = useState(false);
  const [parsedPreview, setParsedPreview] = useState(null);
  const [isConfirming, setIsConfirming] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [scheduleResult, setScheduleResult] = useState(null);

  // Manual Schedule Modal State
  const [showManualModal, setShowManualModal] = useState(false);
  const [activeMembers, setActiveMembers] = useState([]);
  const [manualForm, setManualForm] = useState({
    meeting_title: '',
    agenda: '',
    date: '',
    time: '',
    duration_minutes: 30,
    selected_participant_ids: []
  });

  // Meeting Lists State
  const [meetingsData, setMeetingsData] = useState({
    upcoming_meetings: [],
    today_meetings: [],
    active_meetings: [],
    completed_meetings: [],
    cancelled_meetings: []
  });
  const [isLoading, setIsLoading] = useState(true);

  // Example Prompts
  const exampleCommands = [
    'Schedule a Sprint Planning meeting tomorrow at 10 PM with all active team members.',
    'Schedule a project review meeting on November 28 at 6 PM with Arun and Priya.',
    'Schedule an Architecture Sync today at 4:30 PM for 45 minutes.'
  ];

  useEffect(() => {
    fetchUpcomingMeetings();
    fetchActiveMembers();
    const interval = setInterval(fetchUpcomingMeetings, 15000); // 15s refresh for countdowns
    return () => clearInterval(interval);
  }, [teamId]);

  const fetchActiveMembers = async () => {
    try {
      const res = await api.get('/team/members?status=active');
      const members = res.data?.members || [];
      setActiveMembers(members);
      setManualForm((prev) => ({
        ...prev,
        selected_participant_ids: members.map((m) => m.member_id)
      }));
    } catch (err) {
      console.error('Failed to load active members:', err);
    }
  };

  const handleManualSchedule = async (e) => {
    e.preventDefault();
    if (!manualForm.meeting_title.trim()) {
      setErrorMessage('Meeting title is required.');
      return;
    }
    if (!manualForm.date || !manualForm.time) {
      setErrorMessage('Date and time are required.');
      return;
    }
    if (manualForm.selected_participant_ids.length === 0) {
      setErrorMessage('Please select at least one active team member attendee.');
      return;
    }

    setIsConfirming(true);
    setErrorMessage('');
    setScheduleResult(null);
    try {
      const response = await api.post('/meetings/schedule', {
        meeting_title: manualForm.meeting_title.trim(),
        agenda: manualForm.agenda.trim() || 'Team sync',
        date: manualForm.date,
        time: manualForm.time,
        timezone: 'Asia/Kolkata',
        duration_minutes: parseInt(manualForm.duration_minutes, 10) || 30,
        selected_participant_ids: manualForm.selected_participant_ids
      });

      setScheduleResult(response.data);
      setShowManualModal(false);
      setManualForm({
        meeting_title: '',
        agenda: '',
        date: '',
        time: '',
        duration_minutes: 30,
        selected_participant_ids: activeMembers.map((m) => m.member_id)
      });
      fetchUpcomingMeetings();
    } catch (err) {
      setErrorMessage(err.response?.data?.detail || 'Failed to schedule meeting.');
    } finally {
      setIsConfirming(false);
    }
  };

  const fetchUpcomingMeetings = async () => {
    try {
      const res = await api.get(`/meetings/upcoming?team_id=${teamId}`);
      setMeetingsData(res.data);
    } catch (err) {
      console.error('Failed to load upcoming meetings:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // Parse natural language command
  const handleParseCommand = async (e) => {
    e?.preventDefault();
    if (!commandInput.trim()) return;

    setIsParsing(true);
    setErrorMessage('');
    setScheduleResult(null);
    setParsedPreview(null);

    try {
      const res = await api.post('/meetings/schedule/parse-command', {
        command: commandInput.trim(),
        timezone: 'Asia/Kolkata'
      });
      setParsedPreview(res.data);
    } catch (err) {
      console.error('Natural language parsing error:', err);
      setErrorMessage(err.response?.data?.detail || 'Failed to parse meeting command. Please try again.');
    } finally {
      setIsParsing(false);
    }
  };

  // Confirm and persist schedule
  const handleConfirmSchedule = async () => {
    if (!parsedPreview?.extracted) return;
    setIsConfirming(true);
    setErrorMessage('');
    setScheduleResult(null);

    try {
      const ext = parsedPreview.extracted;
      const matchedIds = (parsedPreview.matched_participants || []).map((p) => p.member_id);

      const response = await api.post('/meetings/schedule', {
        meeting_title: ext.meeting_title,
        agenda: ext.agenda,
        date: ext.date,
        time: ext.time,
        timezone: ext.timezone || 'Asia/Kolkata',
        duration_minutes: ext.duration_minutes || 30,
        selected_participant_ids: matchedIds
      });

      setScheduleResult(response.data);
      setParsedPreview(null);
      setCommandInput('');
      fetchUpcomingMeetings();
    } catch (err) {
      console.error('Failed to confirm schedule:', err);
      setErrorMessage(err.response?.data?.detail || 'Failed to schedule meeting.');
    } finally {
      setIsConfirming(false);
    }
  };

  // Cancel meeting
  const handleCancelMeeting = async (meetingId) => {
    if (!window.confirm('Are you sure you want to cancel this scheduled meeting?')) return;
    try {
      await api.post(`/meetings/${meetingId}/cancel`);
      fetchUpcomingMeetings();
    } catch (err) {
      alert('Failed to cancel meeting: ' + (err.response?.data?.detail || err.message));
    }
  };

  // Join meeting action
  const handleJoinMeeting = (meeting) => {
    const roomId = meeting.room_id || meeting.meeting_id;
    navigate(`/live-meeting?room=${roomId}&meeting_id=${meeting.meeting_id}&title=${encodeURIComponent(meeting.meeting_title)}&join=true`);
  };

  // Format countdown
  const formatCountdown = (totalSeconds) => {
    if (totalSeconds <= 0) return 'Joinable now';
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    if (hours > 24) {
      const days = Math.floor(hours / 24);
      return `Starts in ${days}d ${hours % 24}h`;
    }
    if (hours > 0) {
      return `Starts in ${hours}h ${minutes}m`;
    }
    return `Starts in ${minutes}m`;
  };

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h2 className="text-xl font-bold text-[#0F172A] tracking-tight flex items-center gap-2">
              <CalendarClock className="w-5 h-5 text-[#2563EB]" />
              <span>Upcoming & Scheduled Meetings</span>
            </h2>
            <span className="text-[10px] px-2.5 py-0.5 rounded-full font-bold bg-[#EFF6FF] text-[#2563EB] border border-[#BFDBFE]">
              Natural Language AI Scheduler
            </span>
          </div>
          <p className="text-xs text-[#64748B] mt-0.5">
            Speak or type meeting requirements in plain English. AI extracts dates, attendees, agendas, and dispatches automated invites.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {isLeader && (
            <button
              onClick={() => setShowManualModal(true)}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold shadow-xs cursor-pointer transition"
            >
              <Calendar className="w-3.5 h-3.5" />
              <span>Schedule Manually</span>
            </button>
          )}

          <button
            onClick={fetchUpcomingMeetings}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-[#CBD5E1] bg-white hover:bg-[#F8FAFC] text-xs font-semibold text-[#0F172A] shadow-xs cursor-pointer"
          >
            <RotateCcw className="w-3.5 h-3.5 text-[#2563EB]" />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Alerts */}
      {errorMessage && (
        <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <button onClick={() => setErrorMessage('')}><X className="w-3.5 h-3.5" /></button>
        </div>
      )}

      {scheduleResult && (
        <div className="p-3.5 rounded-xl bg-white border border-[#CBD5E1] text-xs space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-emerald-800">
              <CheckCircle2 className="w-4 h-4 flex-shrink-0 text-[#059669]" />
              <span className="font-semibold">Meeting saved: {scheduleResult.meeting_title} ({scheduleResult.meeting_id})</span>
            </div>
            <button onClick={() => setScheduleResult(null)}><X className="w-3.5 h-3.5" /></button>
          </div>
          {scheduleResult.meeting_link && (
            <a className="block text-[#2563EB] underline break-all" href={scheduleResult.meeting_link} target="_blank" rel="noreferrer">
              {scheduleResult.meeting_link}
            </a>
          )}
          <p className={
            scheduleResult.invitation_dispatch_status === 'success' ? 'text-emerald-700'
              : scheduleResult.invitation_dispatch_status === 'failed' ? 'text-rose-700'
                : 'text-amber-800'
          }>
            Invitation dispatch: {scheduleResult.invitation_dispatch_status || 'unknown'}
            {scheduleResult.invitation_dispatch_error ? ` — ${scheduleResult.invitation_dispatch_error}` : ''}
          </p>
        </div>
      )}

      {/* 1. Natural Language Command Area */}
      {isLeader && (
      <div className="p-6 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm space-y-4">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-[#7C3AED]" />
          <h3 className="text-xs font-bold text-[#0F172A]">Natural Language Meeting Command</h3>
        </div>

        <form onSubmit={handleParseCommand} className="space-y-3">
          <div className="flex flex-col sm:flex-row gap-2.5">
            <input
              type="text"
              value={commandInput}
              onChange={(e) => setCommandInput(e.target.value)}
              placeholder="e.g. Schedule a Sprint Planning meeting tomorrow at 10 PM with all active team members."
              className="flex-1 px-4 py-2.5 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1] text-xs font-medium text-[#0F172A] focus:bg-white focus:border-[#2563EB] transition"
            />
            <button
              type="submit"
              disabled={isParsing || !commandInput.trim()}
              className="flex items-center justify-center gap-2 px-6 py-2.5 rounded-xl bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-bold shadow-xs transition cursor-pointer disabled:opacity-50"
            >
              {isParsing ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Parsing with AI...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5 text-yellow-300" />
                  <span>Parse with AI</span>
                </>
              )}
            </button>
          </div>

          {/* Quick Example Pills */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1 text-[11px] text-[#64748B]">
            <span className="font-semibold whitespace-nowrap">Try asking:</span>
            {exampleCommands.map((cmd, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => setCommandInput(cmd)}
                className="px-2.5 py-1 rounded-lg bg-[#F1F5F9] hover:bg-[#E2E8F0] text-[#0F172A] transition whitespace-nowrap cursor-pointer text-left"
              >
                "{cmd}"
              </button>
            ))}
          </div>
        </form>

        {/* 2. Structured Meeting Preview with Confirm Schedule & Cancel */}
        {parsedPreview && (
          <div className="p-5 rounded-xl bg-[#F8FAFC] border border-[#BFDBFE] space-y-4 animate-scale-in">
            <div className="flex items-center justify-between border-b border-[#E2E8F0] pb-2.5">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-[#2563EB]" />
                <h4 className="text-xs font-bold text-[#0F172A]">AI Extracted Meeting Preview</h4>
              </div>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-[#EFF6FF] text-[#2563EB]">
                {parsedPreview.extracted?.timezone || 'Asia/Kolkata'}
              </span>
            </div>

            {parsedPreview.extracted?.is_ambiguous ? (
              <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs flex items-center gap-2">
                <HelpCircle className="w-4 h-4 flex-shrink-0 text-amber-600" />
                <span>{parsedPreview.extracted?.clarification_question || 'Please provide more details on the date or time.'}</span>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div className="space-y-2">
                  <div>
                    <span className="text-[#64748B] block text-[10px]">Meeting Title</span>
                    <strong className="text-sm text-[#0F172A]">{parsedPreview.extracted?.meeting_title}</strong>
                  </div>
                  <div>
                    <span className="text-[#64748B] block text-[10px]">Agenda / Objective</span>
                    <p className="text-[#0F172A] font-medium">{parsedPreview.extracted?.agenda}</p>
                  </div>
                </div>

                <div className="space-y-2">
                  <div>
                    <span className="text-[#64748B] block text-[10px]">Scheduled Local Time</span>
                    <strong className="text-xs text-[#2563EB]">{parsedPreview.formatted_local_time}</strong>
                    <span className="text-[10px] text-[#64748B] block font-mono mt-0.5">
                      Duration: {parsedPreview.extracted?.duration_minutes} minutes
                    </span>
                  </div>

                  <div>
                    <span className="text-[#64748B] block text-[10px]">Invited Attendees ({parsedPreview.matched_participants?.length || 0})</span>
                    <div className="flex flex-wrap gap-1.5 mt-1">
                      {parsedPreview.matched_participants?.map((p) => (
                        <span key={p.member_id} className="px-2 py-0.5 rounded-md bg-white border border-[#CBD5E1] text-[10px] font-semibold text-[#0F172A]">
                          {p.name} ({p.role})
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Confirm & Cancel Buttons */}
            <div className="flex items-center justify-end gap-2 pt-3 border-t border-[#E2E8F0]">
              <button
                type="button"
                onClick={() => setParsedPreview(null)}
                className="px-4 py-2 rounded-xl border border-[#CBD5E1] text-xs font-semibold text-[#64748B] hover:bg-[#F1F5F9] cursor-pointer"
              >
                Cancel
              </button>
              
              <button
                type="button"
                disabled={isConfirming || parsedPreview.extracted?.is_ambiguous}
                onClick={handleConfirmSchedule}
                className="flex items-center gap-1.5 px-5 py-2 rounded-xl bg-[#059669] hover:bg-[#047857] text-white text-xs font-bold shadow-xs transition cursor-pointer disabled:opacity-50"
              >
                {isConfirming ? (
                  <span>Scheduling...</span>
                ) : (
                  <>
                    <Check className="w-3.5 h-3.5" />
                    <span>Confirm Schedule</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
      )}

      {/* 3. Meetings List: Active & Upcoming */}
      <div className="space-y-4">
        
        {/* Active In-Progress Meetings */}
        {meetingsData.active_meetings?.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-ping" />
              <h3 className="text-xs font-bold text-[#0F172A] uppercase tracking-wider">
                Live In-Progress Meetings ({meetingsData.active_meetings.length})
              </h3>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {meetingsData.active_meetings.map((m) => (
                <div key={m.meeting_id} className="p-4 rounded-xl bg-white border-2 border-red-500 shadow-sm flex items-center justify-between">
                  <div className="space-y-1">
                    <span className="text-[10px] px-2 py-0.5 rounded-md bg-red-50 text-red-700 font-bold border border-red-200">
                      LIVE NOW
                    </span>
                    <h4 className="text-sm font-bold text-[#0F172A]">{m.meeting_title}</h4>
                    <p className="text-[11px] text-[#64748B]">{m.agenda}</p>
                  </div>
                  <button
                    onClick={() => handleJoinMeeting(m)}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-red-600 hover:bg-red-700 text-white text-xs font-bold shadow-sm transition cursor-pointer"
                  >
                    <Radio className="w-3.5 h-3.5 animate-pulse" />
                    <span>Join Room</span>
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Upcoming Meetings List */}
        <div className="p-6 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-[#0F172A]">Scheduled Meetings</h3>
            <span className="text-xs text-[#64748B]">
              {meetingsData.upcoming_meetings?.length || 0} Scheduled
            </span>
          </div>

          {isLoading ? (
            <div className="py-8 text-center text-xs text-[#64748B]">
              Loading scheduled meetings...
            </div>
          ) : meetingsData.upcoming_meetings?.length === 0 ? (
            <div className="p-8 text-center text-xs text-[#64748B] space-y-2">
              <CalendarClock className="w-8 h-8 text-[#CBD5E1] mx-auto" />
              <p>{isLeader ? 'No upcoming meetings scheduled. Use the command box above to schedule one with your team!' : 'No upcoming meetings are scheduled.'}</p>
            </div>
          ) : (
            <div className="divide-y divide-[#E2E8F0]">
              {meetingsData.upcoming_meetings.map((m) => (
                <div key={m.meeting_id} className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-xs text-[#0F172A]">{m.meeting_title}</span>
                      <span className={`text-[10px] px-2 py-0.5 rounded-md font-semibold border ${
                        m.is_joinable 
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200 animate-pulse'
                          : 'bg-[#EFF6FF] text-[#2563EB] border-[#BFDBFE]'
                      }`}>
                        {m.is_joinable ? 'Joinable Now' : formatCountdown(m.time_until_start_seconds)}
                      </span>
                    </div>

                    <div className="flex items-center gap-3 text-[11px] text-[#64748B]">
                      <span className="flex items-center gap-1">
                        <Clock className="w-3.5 h-3.5" />
                        <span>{new Date(m.scheduled_start_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}</span>
                      </span>
                      <span>•</span>
                      <span className="flex items-center gap-1">
                        <Users className="w-3.5 h-3.5" />
                        <span>{m.participants?.length || 0} Attendees</span>
                      </span>
                    </div>

                    <p className="text-[11px] text-[#475569]">Host: <strong className="text-[#0F172A]">{m.host_name || 'Team Leader'}</strong></p>
                    {m.agenda && <p className="text-[11px] text-[#475569]">{m.agenda}</p>}
                    {m.meeting_link && (
                      <a className="block text-[11px] text-[#2563EB] underline break-all" href={m.meeting_link} target="_blank" rel="noreferrer">
                        Meeting link
                      </a>
                    )}
                    {isLeader && m.invitation_dispatch_status && (
                      <p className={`text-[11px] ${m.invitation_dispatch_status === 'success' ? 'text-emerald-700' : 'text-amber-800'}`}>
                        Invitation dispatch: {m.invitation_dispatch_status}
                        {m.invitation_dispatch_error ? ` — ${m.invitation_dispatch_error}` : ''}
                      </p>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    {m.is_joinable ? (
                      <button
                        onClick={() => handleJoinMeeting(m)}
                        className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#059669] hover:bg-[#047857] text-white text-xs font-bold shadow-xs transition cursor-pointer"
                      >
                        <Play className="w-3.5 h-3.5 fill-current" />
                        <span>Join Meeting</span>
                      </button>
                    ) : (
                      <span className="text-[11px] text-[#64748B] italic px-3 py-1.5 rounded-lg bg-[#F8FAFC] border border-[#E2E8F0]">
                        Join opens 5m prior
                      </span>
                    )}

                    {(m.host_id === user?.user_id || (m.host_email || '').toLowerCase() === (user?.email || '').toLowerCase()) && (
                      <button
                        onClick={() => handleCancelMeeting(m.meeting_id)}
                        className="px-3 py-1.5 rounded-xl border border-[#CBD5E1] text-[#64748B] hover:text-rose-600 hover:bg-rose-50 text-xs font-semibold transition cursor-pointer"
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>

      {/* Manual Schedule Modal */}
      {showManualModal && isLeader && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-lg w-full max-h-[90vh] overflow-y-auto p-6 space-y-4 border border-[#E2E8F0] shadow-2xl animate-scale-in">
            <div className="flex items-center justify-between pb-2 border-b border-[#E2E8F0]">
              <div className="space-y-0.5">
                <h3 className="text-base font-bold text-[#0F172A]">Schedule Meeting Manually</h3>
                <p className="text-[11px] text-[#64748B]">Create a scheduled meeting with verified MongoDB active team members.</p>
              </div>
              <button
                type="button"
                onClick={() => setShowManualModal(false)}
                className="p-1 rounded-lg text-[#64748B] hover:text-[#0F172A]"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleManualSchedule} className="space-y-3.5 text-xs">
              <div>
                <label className="block font-semibold text-[#0F172A] mb-1">Meeting Title *</label>
                <input
                  type="text"
                  required
                  value={manualForm.meeting_title}
                  onChange={(e) => setManualForm({ ...manualForm, meeting_title: e.target.value })}
                  placeholder="e.g. Sprint Architecture Alignment"
                  className="w-full px-3.5 py-2 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1] text-[#0F172A] text-xs focus:bg-white focus:border-[#2563EB]"
                />
              </div>

              <div>
                <label className="block font-semibold text-[#0F172A] mb-1">Agenda / Objective</label>
                <textarea
                  rows={2}
                  value={manualForm.agenda}
                  onChange={(e) => setManualForm({ ...manualForm, agenda: e.target.value })}
                  placeholder="Brief meeting objectives and expected deliverables..."
                  className="w-full px-3.5 py-2 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1] text-[#0F172A] text-xs focus:bg-white focus:border-[#2563EB]"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-[#0F172A] mb-1">Date *</label>
                  <input
                    type="date"
                    required
                    min={new Date().toISOString().split('T')[0]}
                    value={manualForm.date}
                    onChange={(e) => setManualForm({ ...manualForm, date: e.target.value })}
                    className="w-full px-3.5 py-2 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1] text-[#0F172A] text-xs focus:bg-white focus:border-[#2563EB]"
                  />
                </div>

                <div>
                  <label className="block font-semibold text-[#0F172A] mb-1">Time (24h) *</label>
                  <input
                    type="time"
                    required
                    value={manualForm.time}
                    onChange={(e) => setManualForm({ ...manualForm, time: e.target.value })}
                    className="w-full px-3.5 py-2 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1] text-[#0F172A] text-xs focus:bg-white focus:border-[#2563EB]"
                  />
                </div>
              </div>

              <div>
                <label className="block font-semibold text-[#0F172A] mb-1">Duration</label>
                <select
                  value={manualForm.duration_minutes}
                  onChange={(e) => setManualForm({ ...manualForm, duration_minutes: parseInt(e.target.value, 10) })}
                  className="w-full px-3.5 py-2 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1] text-[#0F172A] text-xs cursor-pointer focus:bg-white focus:border-[#2563EB]"
                >
                  <option value={15}>15 Minutes</option>
                  <option value={30}>30 Minutes</option>
                  <option value={45}>45 Minutes</option>
                  <option value={60}>60 Minutes</option>
                  <option value={90}>90 Minutes</option>
                </select>
              </div>

              <div>
                <label className="block font-semibold text-[#0F172A] mb-1">
                  Invite Active Team Members ({manualForm.selected_participant_ids.length}/{activeMembers.length})
                </label>
                <div className="max-h-36 overflow-y-auto space-y-1.5 p-2.5 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1]">
                  {activeMembers.length === 0 ? (
                    <p className="text-[11px] text-[#64748B]">No active members found.</p>
                  ) : (
                    activeMembers.map((m) => {
                      const isChecked = manualForm.selected_participant_ids.includes(m.member_id);
                      return (
                        <label
                          key={m.member_id}
                          className="flex items-center gap-2 p-1.5 rounded-lg hover:bg-white text-[11px] cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setManualForm((prev) => ({
                                  ...prev,
                                  selected_participant_ids: [...prev.selected_participant_ids, m.member_id]
                                }));
                              } else {
                                setManualForm((prev) => ({
                                  ...prev,
                                  selected_participant_ids: prev.selected_participant_ids.filter((id) => id !== m.member_id)
                                }));
                              }
                            }}
                            className="rounded text-[#2563EB]"
                          />
                          <span className="font-semibold text-[#0F172A]">{m.name}</span>
                          <span className="text-[#64748B]">({m.role})</span>
                        </label>
                      );
                    })
                  )}
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-[#E2E8F0]">
                <button
                  type="button"
                  onClick={() => setShowManualModal(false)}
                  className="px-4 py-2 rounded-xl border border-[#CBD5E1] text-[#64748B] hover:bg-[#F1F5F9] font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isConfirming}
                  className="px-5 py-2 rounded-xl bg-[#2563EB] hover:bg-[#1D4ED8] text-white font-bold shadow-xs transition cursor-pointer disabled:opacity-50"
                >
                  {isConfirming ? 'Scheduling...' : 'Save & Schedule'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
}
