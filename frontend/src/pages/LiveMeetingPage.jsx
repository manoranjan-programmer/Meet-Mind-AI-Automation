import React, { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { 
  Mic, 
  MicOff,
  Video,
  VideoOff,
  PhoneOff,
  Subtitles,
  MessageSquare,
  Users, 
  CheckCircle2,
  AlertCircle,
  Download,
  Check,
  X,
  Cpu,
  Sparkles,
  Edit3,
  Calendar,
  Radio,
  Share2,
  Monitor,
  MonitorOff,
  Send,
  Info,
  RotateCcw,
  Pause,
  Play,
  Volume2,
  Copy,
  Maximize,
  Minimize,
  Shield,
  UserPlus,
  CalendarClock,
  Plus,
  Keyboard,
  Clock,
  ArrowRight,
  ChevronDown,
  ExternalLink,
  Trash2,
  Eye,
  Link2,
  ShieldCheck,
  MoreVertical
} from 'lucide-react';
import api, { getWebSocketUrl } from '../services/api';
import { useAuth } from '../context/AuthContext';

const ICE_SERVERS = {
  iceServers: [
    { urls: ['stun:stun.l.google.com:19302', 'stun:stun1.l.google.com:19302'] }
  ]
};

export default function LiveMeetingPage() {
  const { user } = useAuth();
  const isLeader = ['admin', 'team lead', 'team leader', 'team_leader', 'manager', 'team lead / admin', 'team leader / admin'].includes(
    (user?.role || '').toLowerCase()
  );
  const location = useLocation();
  const navigate = useNavigate();
  const searchParams = new URLSearchParams(location.search);
  const initialRoomId = searchParams.get('room') || '';
  const initialTitle = searchParams.get('title') || 'Sprint Planning & Feature Sync';
  const initialMeetingId = searchParams.get('meeting_id') || searchParams.get('id') || '';
  const autoJoin = searchParams.get('join') === 'true';

  // Conference vs Landing Hub Mode (Default is Landing Hub)
  const [inConference, setInConference] = useState(Boolean(initialRoomId && autoJoin));

  // Google Meet Landing Hub State
  const [hubTab, setHubTab] = useState('upcoming'); // 'upcoming' | 'recent'
  const [upcomingMeetings, setUpcomingMeetings] = useState([]);
  const [recentMeetings, setRecentMeetings] = useState([]);
  const [isLoadingUpcoming, setIsLoadingUpcoming] = useState(true);
  const [isLoadingRecent, setIsLoadingRecent] = useState(false);
  const [codeOrLinkInput, setCodeOrLinkInput] = useState('');
  const [isNewMeetingDropdownOpen, setIsNewMeetingDropdownOpen] = useState(false);

  // Modals State
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [showLaterLinkModal, setShowLaterLinkModal] = useState(false);
  const [selectedMeeting, setSelectedMeeting] = useState(null);
  const [createdLaterMeeting, setCreatedLaterMeeting] = useState(null);

  // Scheduling Form
  const [scheduleForm, setScheduleForm] = useState({
    meeting_title: '',
    description: '',
    date: new Date().toISOString().split('T')[0],
    time: '14:00',
    duration_minutes: 30,
    agenda: '',
    selected_participant_ids: []
  });
  const [isSubmittingSchedule, setIsSubmittingSchedule] = useState(false);
  const [scheduleResult, setScheduleResult] = useState(null);

  // Live Clock
  const [currentTime, setCurrentTime] = useState(new Date());

  // Room & Meeting State
  const [roomId, setRoomId] = useState(initialRoomId);
  const [meetingTitle, setMeetingTitle] = useState(initialTitle);
  const [currentMeetingId, setCurrentMeetingId] = useState(initialMeetingId);
  const [isMeetingActive, setIsMeetingActive] = useState(false);
  const [isRecordingPaused, setIsRecordingPaused] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [audioLevel, setAudioLevel] = useState(0);
  const [errorMessage, setErrorMessage] = useState('');
  const [vadNotice, setVadNotice] = useState('');
  const [failedAudioBlob, setFailedAudioBlob] = useState(null);
  const [failedAudioDuration, setFailedAudioDuration] = useState('');
  const [copiedLink, setCopiedLink] = useState(false);
  const [participantNotice, setParticipantNotice] = useState('');
  const [isFullScreen, setIsFullScreen] = useState(false);

  // Active Team Members & Selection
  const [activeMembers, setActiveMembers] = useState([]);
  const [selectedMemberIds, setSelectedMemberIds] = useState(new Set());
  const [isLoadingMembers, setIsLoadingMembers] = useState(true);

  // WebRTC Controls & Streams
  const [isMicMuted, setIsMicMuted] = useState(false);
  const [isCamEnabled, setIsCamEnabled] = useState(false);
  const [isScreenSharing, setIsScreenSharing] = useState(false);
  const [showClosedCaptions, setShowClosedCaptions] = useState(true);
  const [activeSpeakerId, setActiveSpeakerId] = useState('user_local');
  const [isSidePanelOpen, setIsSidePanelOpen] = useState(true);
  const [sidePanelTab, setSidePanelTab] = useState('transcript'); // 'transcript' | 'intel' | 'tasks' | 'people' | 'chat'

  const copyMeetingLink = () => {
    const effectiveId = roomId || currentMeetingId || 'room';
    const link = `${window.location.origin}/live-meeting?room=${encodeURIComponent(effectiveId)}&title=${encodeURIComponent(meetingTitle)}`;
    navigator.clipboard.writeText(link);
    setCopiedLink(true);
    setTimeout(() => setCopiedLink(false), 2500);
  };

  const toggleFullScreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen?.().catch(() => {});
      setIsFullScreen(true);
    } else {
      document.exitFullscreen?.().catch(() => {});
      setIsFullScreen(false);
    }
  };

  // WebRTC Remote Peers & Meeting Chat
  const [remotePeers, setRemotePeers] = useState([]); // [{ peer_id, name, role, stream, video_enabled, audio_enabled }]
  const [inMeetingMessages, setInMeetingMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [latestSubtitle, setLatestSubtitle] = useState({ speaker: '', text: '' });

  // Multi-Agent Workflow Execution State
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingStep, setProcessingStep] = useState(0);
  const [currentMeeting, setCurrentMeeting] = useState(null);
  const isMeetingHost = Boolean(
    currentMeeting?.host_id === user?.user_id ||
    ((currentMeeting?.host_email || '').toLowerCase() && (currentMeeting?.host_email || '').toLowerCase() === (user?.email || '').toLowerCase())
  );
  const [transcripts, setTranscripts] = useState([]);
  const [extractedTasks, setExtractedTasks] = useState([]);
  const [approvedTaskIds, setApprovedTaskIds] = useState(new Set());
  const [rejectedTaskIds, setRejectedTaskIds] = useState(new Set());
  const [editingTask, setEditingTask] = useState(null);
  const [diagnosticsData, setDiagnosticsData] = useState(null);
  const [isLoadingDiagnostics, setIsLoadingDiagnostics] = useState(false);
  const [showMoreMenu, setShowMoreMenu] = useState(false);

  const isMeetingHostUser = (meeting) => Boolean(
    meeting?.host_id === user?.user_id ||
    ((meeting?.host_email || '').toLowerCase() && (meeting?.host_email || '').toLowerCase() === (user?.email || '').toLowerCase())
  );

  const fetchDiagnostics = async (meetingIdToFetch) => {
    const targetMid = meetingIdToFetch || currentMeetingId;
    if (!targetMid) return;
    setIsLoadingDiagnostics(true);
    try {
      const res = await api.get(`/meetings/${targetMid}/diagnostics`);
      setDiagnosticsData(res.data);
    } catch (err) {
      console.error('Failed to load diagnostics:', err);
    } finally {
      setIsLoadingDiagnostics(false);
    }
  };

  // Stream Refs
  const localStreamRef = useRef(null);
  const localVideoRef = useRef(null);
  const screenTrackRef = useRef(null);
  const screenPreviewRef = useRef(null);
  const peersRef = useRef(new Map()); // peer_id -> RTCPeerConnection
  const wsSignalingRef = useRef(null);
  const myPeerIdRef = useRef(`peer_${Math.random().toString(36).substring(2, 9)}`);

  // Audio Recording & Web Audio API Mixer Refs
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const timerIntervalRef = useRef(null);
  const chunkIntervalRef = useRef(null);
  const activeSpeakerNameRef = useRef('You');
  const audioContextRef = useRef(null);
  const audioDestinationRef = useRef(null);
  const analyserNodeRef = useRef(null);
  const animFrameRef = useRef(null);
  const waveformCanvasRef = useRef(null);
  const recordingTimeRef = useRef(0);
  const currentMeetingIdRef = useRef(initialMeetingId);
  const recorderMimeTypeRef = useRef('audio/webm');
  const hasDetectedSoundRef = useRef(false);
  const silentSecondsRef = useRef(0);

  // Microphone Permission & Device Selection State
  const [micPermission, setMicPermission] = useState('unknown'); // 'granted' | 'prompt' | 'denied' | 'unknown'
  const [audioInputDevices, setAudioInputDevices] = useState([]);
  const [selectedMicId, setSelectedMicId] = useState('');
  const [micStatusWarning, setMicStatusWarning] = useState('');

  // Keep currentMeetingIdRef synced with state
  useEffect(() => {
    currentMeetingIdRef.current = currentMeetingId;
  }, [currentMeetingId]);

  // Attach shared screen track to presentation preview video element
  useEffect(() => {
    if (isScreenSharing && screenPreviewRef.current && screenTrackRef.current) {
      screenPreviewRef.current.srcObject = new MediaStream([screenTrackRef.current]);
    } else if (!isScreenSharing && screenPreviewRef.current) {
      screenPreviewRef.current.srcObject = null;
    }
  }, [isScreenSharing]);

  // Enumerate microphone devices & permission state
  const refreshAudioDevices = async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const mics = devices.filter((d) => d.kind === 'audioinput');
      setAudioInputDevices(mics);
      if (mics.length > 0 && !selectedMicId) {
        setSelectedMicId(mics[0].deviceId);
      }
    } catch (err) {
      console.warn('Could not enumerate audio devices:', err);
    }
  };

  useEffect(() => {
    refreshAudioDevices();
    if (navigator.permissions?.query) {
      navigator.permissions.query({ name: 'microphone' }).then((perm) => {
        setMicPermission(perm.state);
        perm.onchange = () => setMicPermission(perm.state);
      }).catch(() => {});
    }
    const handleDeviceChange = () => refreshAudioDevices();
    navigator.mediaDevices?.addEventListener?.('devicechange', handleDeviceChange);
    return () => {
      navigator.mediaDevices?.removeEventListener?.('devicechange', handleDeviceChange);
    };
  }, []);

  // Safe MIME Type resolver across browsers
  const getSupportedMimeType = () => {
    const candidates = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/ogg',
      'audio/mp4',
      'audio/aac',
      'audio/wav'
    ];
    for (const c of candidates) {
      if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(c)) {
        return c;
      }
    }
    return '';
  };

  const getExtensionForMime = (mime) => {
    const m = (mime || '').toLowerCase();
    if (m.includes('mp4') || m.includes('m4a') || m.includes('aac')) return 'm4a';
    if (m.includes('ogg')) return 'ogg';
    if (m.includes('wav')) return 'wav';
    if (m.includes('mpeg') || m.includes('mp3')) return 'mp3';
    return 'webm';
  };

  const agentSteps = [
    { id: 1, name: 'Recording', desc: 'Capturing microphone & meeting audio chunks' },
    { id: 2, name: 'Uploading audio', desc: 'Uploading complete audio recording to server' },
    { id: 3, name: 'Validating audio', desc: 'Checking audio format, duration, sample rate & speech signal' },
    { id: 4, name: 'Transcribing', desc: 'Groq Whisper Speech-to-Text transcription' },
    { id: 5, name: 'Identifying speakers', desc: 'Speaker diarization & participant attribution' },
    { id: 6, name: 'Analyzing meeting', desc: 'Groq AI summary, topics & key decisions' },
    { id: 7, name: 'Extracting tasks', desc: 'Action item extraction, responsibility & skill matching' },
    { id: 8, name: 'Ready for review', desc: 'Analysis complete and ready for human approval' },
  ];

  // 1. Initial Load: Fetch Active Team Members & Check Room
  useEffect(() => {
    fetchActiveMembers();
  }, [user]);

  const fetchActiveMembers = async () => {
    setIsLoadingMembers(true);
    try {
      const res = await api.get('/team/members?status=active');
      const members = res.data?.members || [];
      setActiveMembers(members);
      const allIds = new Set(members.map((m) => m.member_id));
      setSelectedMemberIds(allIds);
    } catch (err) {
      console.error('Failed to load active members:', err);
    } finally {
      setIsLoadingMembers(false);
    }
  };

  // Real-time Clock
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Fetch upcoming meetings from MongoDB Atlas
  const fetchUpcomingMeetings = async () => {
    setIsLoadingUpcoming(true);
    try {
      const res = await api.get(`/meetings/upcoming?team_id=${user?.team_id || ''}`);
      setUpcomingMeetings(res.data?.upcoming_meetings || []);
    } catch (err) {
      console.error('Failed to load upcoming meetings:', err);
    } finally {
      setIsLoadingUpcoming(false);
    }
  };

  // Fetch recent completed meetings from MongoDB
  const fetchRecentMeetings = async () => {
    setIsLoadingRecent(true);
    try {
      const res = await api.get('/meetings');
      setRecentMeetings(res.data?.meetings || []);
    } catch (err) {
      console.error('Failed to load recent meetings:', err);
    } finally {
      setIsLoadingRecent(false);
    }
  };

  useEffect(() => {
    if (!inConference) {
      fetchUpcomingMeetings();
      fetchRecentMeetings();
    }
  }, [inConference, user]);

  // Handle auto-join from URL params if explicitly requested
  useEffect(() => {
    if (autoJoin && initialRoomId) {
      setInConference(true);
      setTimeout(() => {
        handleStartMeeting(initialRoomId, initialMeetingId || initialRoomId, initialTitle);
      }, 200);
    }
  }, []);

  // Action: Start Instant Meeting
  const handleStartInstantMeeting = async () => {
    setIsNewMeetingDropdownOpen(false);
    setErrorMessage('');
    try {
      const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const res = await api.post('/meetings/start', {
        meeting_title: `Instant Meeting (${timeStr})`,
        selected_participant_ids: []
      });
      const created = res.data;
      setCurrentMeeting(created);
      const mid = created.meeting_id;
      const rid = created.room_id || mid;
      setCurrentMeetingId(mid);
      setRoomId(rid);
      setMeetingTitle(created.meeting_title);
      setInConference(true);

      setTimeout(() => {
        handleStartMeeting(rid, mid, created.meeting_title);
      }, 100);
    } catch (err) {
      setErrorMessage('Failed to start instant meeting: ' + (err.response?.data?.detail || err.message));
    }
  };

  // Action: Create Meeting For Later
  const handleCreateMeetingForLater = async () => {
    setIsNewMeetingDropdownOpen(false);
    try {
      const today = new Date().toISOString().split('T')[0];
      const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const payload = {
        meeting_title: `Quick Meeting (${timeStr})`,
        description: 'Meeting created for later',
        agenda: 'Team sync and discussion',
        date: today,
        time: '18:00',
        duration_minutes: 30,
        selected_participant_ids: []
      };
      const res = await api.post('/meetings/schedule', payload);
      const meeting = res.data;
      setCreatedLaterMeeting({
        meeting_id: meeting.meeting_id,
        room_id: meeting.room_id,
        join_url: meeting.meeting_link,
        invitation_dispatch: meeting.invitation_dispatch
      });
      setShowLaterLinkModal(true);
      fetchUpcomingMeetings();
    } catch (err) {
      setErrorMessage('Failed to create meeting: ' + (err.response?.data?.detail || err.message));
    }
  };

  // Action: Start Scheduled Meeting (Host only)
  const handleStartScheduledMeeting = async (meeting) => {
    setErrorMessage('');
    try {
      const res = await api.post(`/meetings/${meeting.meeting_id}/start-session`);
      const started = res.data;
      setCurrentMeeting(started);
      const mid = started.meeting_id;
      const rid = started.room_id || mid;
      setCurrentMeetingId(mid);
      setRoomId(rid);
      setMeetingTitle(started.meeting_title || meeting.meeting_title);
      setInConference(true);

      setTimeout(() => {
        handleStartMeeting(rid, mid, started.meeting_title || meeting.meeting_title);
      }, 100);
    } catch (err) {
      alert('Failed to start scheduled meeting: ' + (err.response?.data?.detail || err.message));
    }
  };

  // Action: Join Scheduled Meeting (Participant or live meeting)
  const handleJoinScheduledMeeting = (meeting) => {
    const mid = meeting.meeting_id;
    const rid = meeting.room_id || mid;
    setCurrentMeeting(meeting);
    setCurrentMeetingId(mid);
    setRoomId(rid);
    setMeetingTitle(meeting.meeting_title);
    setInConference(true);

    setTimeout(() => {
      handleStartMeeting(rid, mid, meeting.meeting_title);
    }, 100);
  };

  // Action: Join with a Meeting Code or Link
  const handleJoinWithCode = async (e) => {
    e?.preventDefault();
    const raw = codeOrLinkInput.trim();
    if (!raw) return;

    let targetCode = raw;
    if (raw.includes('room=')) {
      try {
        const url = new URL(raw, window.location.origin);
        targetCode = url.searchParams.get('room') || raw;
      } catch {
        const match = raw.match(/room=([^&]+)/);
        if (match) targetCode = match[1];
      }
    }

    try {
      const res = await api.get(`/meetings/room/${encodeURIComponent(targetCode)}`);
      const m = res.data;
      const mid = m.meeting_id || targetCode;
      const rid = m.room_id || targetCode;
      setCurrentMeetingId(mid);
      setRoomId(rid);
      setMeetingTitle(m.meeting_title || 'Live Conference');
      setCurrentMeeting(m);
      setInConference(true);

      setTimeout(() => {
        handleStartMeeting(rid, mid, m.meeting_title || 'Live Conference');
      }, 100);
    } catch (err) {
      setErrorMessage(err.response?.data?.detail || 'Meeting not found or you do not have permission to join it.');
    }
  };

  // Action: Schedule Meeting Form Submit
  const handleScheduleFormSubmit = async (e) => {
    e.preventDefault();
    if (!scheduleForm.meeting_title.trim()) {
      alert('Please enter a meeting title.');
      return;
    }

    setIsSubmittingSchedule(true);
    setScheduleResult(null);
    try {
      const payload = {
        meeting_title: scheduleForm.meeting_title.trim(),
        description: scheduleForm.description.trim(),
        agenda: scheduleForm.agenda.trim() || scheduleForm.description.trim() || 'Team sync',
        date: scheduleForm.date,
        time: scheduleForm.time,
        timezone: 'Asia/Kolkata',
        duration_minutes: Number(scheduleForm.duration_minutes) || 30,
        selected_participant_ids: scheduleForm.selected_participant_ids
      };

      const res = await api.post('/meetings/schedule', payload);
      const created = res.data;

      setShowScheduleModal(false);
      setScheduleResult(created);

      setHubTab('upcoming');
      fetchUpcomingMeetings();

      setScheduleForm({
        meeting_title: '',
        description: '',
        date: new Date().toISOString().split('T')[0],
        time: '14:00',
        duration_minutes: 30,
        agenda: '',
        selected_participant_ids: []
      });
    } catch (err) {
      alert('Failed to schedule meeting: ' + (err.response?.data?.detail || err.message));
    } finally {
      setIsSubmittingSchedule(false);
    }
  };

  // Action: Cancel Scheduled Meeting
  const handleCancelScheduledMeeting = async (meetingId) => {
    if (!window.confirm('Are you sure you want to cancel this scheduled meeting?')) return;
    try {
      await api.post(`/meetings/${meetingId}/cancel`);
      fetchUpcomingMeetings();
    } catch (err) {
      alert('Failed to cancel meeting: ' + (err.response?.data?.detail || err.message));
    }
  };

  // Action: Edit Meeting
  const handleEditMeeting = (meeting) => {
    setSelectedMeeting(meeting);
    setScheduleForm({
      meeting_title: meeting.meeting_title || '',
      description: meeting.description || meeting.agenda || '',
      date: meeting.scheduled_start_at ? meeting.scheduled_start_at.split('T')[0] : new Date().toISOString().split('T')[0],
      time: meeting.scheduled_start_at ? meeting.scheduled_start_at.split('T')[1]?.substring(0, 5) : '14:00',
      duration_minutes: meeting.duration_minutes || 30,
      agenda: meeting.agenda || '',
      selected_participant_ids: meeting.selected_participant_ids || []
    });
    setShowEditModal(true);
  };

  const handleEditFormSubmit = async (e) => {
    e.preventDefault();
    if (!selectedMeeting) return;
    try {
      const payload = {
        meeting_title: scheduleForm.meeting_title.trim(),
        description: scheduleForm.description.trim(),
        agenda: scheduleForm.agenda.trim() || scheduleForm.description.trim() || 'Team sync',
        date: scheduleForm.date,
        time: scheduleForm.time,
        timezone: 'Asia/Kolkata',
        duration_minutes: Number(scheduleForm.duration_minutes) || 30,
        selected_participant_ids: scheduleForm.selected_participant_ids
      };
      await api.post(`/meetings/${selectedMeeting.meeting_id}/edit-schedule`, payload);
      setShowEditModal(false);
      setSelectedMeeting(null);
      fetchUpcomingMeetings();
    } catch (err) {
      alert('Failed to edit meeting: ' + (err.response?.data?.detail || err.message));
    }
  };

  // Action: View Meeting Details
  const handleViewDetails = (meeting) => {
    setSelectedMeeting(meeting);
    setShowDetailsModal(true);
  };

  // Action: Leave Conference & Return to Hub
  const handleLeaveConference = () => {
    cleanupAllMediaAndPeers();
    setIsMeetingActive(false);
    setInConference(false);
    fetchUpcomingMeetings();
    fetchRecentMeetings();
  };

  // Timer Effect
  useEffect(() => {
    if (isMeetingActive) {
      timerIntervalRef.current = setInterval(() => {
        setRecordingTime((prev) => prev + 1);
      }, 1000);
    } else {
      clearInterval(timerIntervalRef.current);
    }
    return () => clearInterval(timerIntervalRef.current);
  }, [isMeetingActive]);

  // Clean up all streams and peer connections on unmount
  useEffect(() => {
    return () => {
      clearInterval(timerIntervalRef.current);
      clearInterval(chunkIntervalRef.current);
      cleanupAllMediaAndPeers();
    };
  }, []);

  const cleanupAllMediaAndPeers = () => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    if (localStreamRef.current) {
      localStreamRef.current.getTracks().forEach((t) => t.stop());
      localStreamRef.current = null;
    }
    if (screenTrackRef.current) {
      screenTrackRef.current.stop();
      screenTrackRef.current = null;
    }
    peersRef.current.forEach((pc) => pc.close());
    peersRef.current.clear();
    if (wsSignalingRef.current) {
      wsSignalingRef.current.close();
      wsSignalingRef.current = null;
    }
  };

  const formatTimer = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  };

  // 2. WEBRTC SIGNALING LIFECYCLE
  const connectSignalingWebSocket = (targetRoomId) => {
    const token = localStorage.getItem('meetmind_token');
    const wsUrl = `${getWebSocketUrl(`/ws/meetings/${targetRoomId}/signaling`)}?token=${encodeURIComponent(token || '')}`;
    const ws = new WebSocket(wsUrl);
    wsSignalingRef.current = ws;

    ws.onopen = () => {
      console.log('[WebRTC Signaling] Connected to room:', targetRoomId);
      // Join room announcement
      ws.send(JSON.stringify({
        event: 'join_room',
        data: {
          peer_id: myPeerIdRef.current,
          user_id: user?.user_id,
          name: user?.name || 'You',
          role: user?.role || 'Member',
          video_enabled: isCamEnabled,
          audio_enabled: !isMicMuted
        }
      }));
    };

    ws.onmessage = async (event) => {
      try {
        const msg = JSON.parse(event.data);
        const { event: eventName, data } = msg;

        if (eventName === 'room_joined') {
          // Connect to existing peers by initiating offers
          const existing = data.existing_peers || [];
          for (const peer of existing) {
            await createPeerConnection(peer.peer_id, peer.name, peer.role, true);
          }
        } else if (eventName === 'peer_joined') {
          // New peer joined room; prepare peer connection
          await createPeerConnection(data.peer_id, data.name, data.role, false);
          setParticipantNotice(`${data.name || 'Participant'} joined the meeting`);
          setTimeout(() => setParticipantNotice(''), 4000);
        } else if (eventName === 'offer') {
          // Handle incoming SDP offer
          const { from_peer_id, signal } = data;
          let pc = peersRef.current.get(from_peer_id);
          if (!pc) {
            pc = await createPeerConnection(from_peer_id, 'Peer', 'Member', false);
          }
          await pc.setRemoteDescription(new RTCSessionDescription(signal));
          const answer = await pc.createAnswer();
          await pc.setLocalDescription(answer);

          ws.send(JSON.stringify({
            event: 'answer',
            data: {
              target_peer_id: from_peer_id,
              signal: answer
            }
          }));
        } else if (eventName === 'answer') {
          // Handle incoming SDP answer
          const { from_peer_id, signal } = data;
          const pc = peersRef.current.get(from_peer_id);
          if (pc) {
            await pc.setRemoteDescription(new RTCSessionDescription(signal));
          }
        } else if (eventName === 'ice_candidate') {
          // Handle incoming ICE candidate
          const { from_peer_id, signal } = data;
          const pc = peersRef.current.get(from_peer_id);
          if (pc && signal) {
            await pc.addIceCandidate(new RTCIceCandidate(signal));
          }
        } else if (eventName === 'track_state_changed') {
          // Update remote peer track states
          setRemotePeers((prev) =>
            prev.map((p) =>
              p.peer_id === data.peer_id
                ? { ...p, video_enabled: data.video_enabled, audio_enabled: data.audio_enabled, screen_sharing: data.screen_sharing }
                : p
            )
          );
        } else if (eventName === 'meeting_chat_message') {
          setInMeetingMessages((prev) => [...prev, data]);
        } else if (eventName === 'peer_left') {
          // Remove peer
          const pc = peersRef.current.get(data.peer_id);
          if (pc) {
            pc.close();
            peersRef.current.delete(data.peer_id);
          }
          setRemotePeers((prev) => prev.filter((p) => p.peer_id !== data.peer_id));
          setParticipantNotice(`${data.name || 'A participant'} left the meeting`);
          setTimeout(() => setParticipantNotice(''), 4000);
        } else if (eventName === 'meeting_ended') {
          handleLeaveMeeting();
        }
      } catch (err) {
        console.error('[WebRTC Signaling] Message processing error:', err);
      }
    };

    ws.onerror = (e) => console.error('[WebRTC Signaling] Socket error:', e);
  };

  // Create RTCPeerConnection for a remote peer
  const createPeerConnection = async (targetPeerId, peerName, peerRole, isInitiator) => {
    const pc = new RTCPeerConnection(ICE_SERVERS);
    peersRef.current.set(targetPeerId, pc);

    // Add local tracks to peer connection
    if (localStreamRef.current) {
      localStreamRef.current.getTracks().forEach((track) => {
        pc.addTrack(track, localStreamRef.current);
      });
    }

    // ICE Candidate handler
    pc.onicecandidate = (event) => {
      if (event.candidate && wsSignalingRef.current?.readyState === WebSocket.OPEN) {
        wsSignalingRef.current.send(JSON.stringify({
          event: 'ice_candidate',
          data: {
            target_peer_id: targetPeerId,
            signal: event.candidate
          }
        }));
      }
    };

    // Remote Track handler
    pc.ontrack = (event) => {
      const remoteStream = event.streams[0];

      // Mix remote peer audio into recording destination
      if (event.track.kind === 'audio' && audioContextRef.current && audioDestinationRef.current) {
        try {
          const rAudioStream = event.streams[0] || new MediaStream([event.track]);
          const remoteSource = audioContextRef.current.createMediaStreamSource(rAudioStream);
          remoteSource.connect(audioDestinationRef.current);
          if (analyserNodeRef.current) {
            remoteSource.connect(analyserNodeRef.current);
          }
        } catch (mixErr) {
          console.debug('Error mixing remote peer audio track:', mixErr);
        }
      }

      setRemotePeers((prev) => {
        const existingIdx = prev.findIndex((p) => p.peer_id === targetPeerId);
        if (existingIdx !== -1) {
          const updated = [...prev];
          updated[existingIdx].stream = remoteStream;
          return updated;
        }
        return [
          ...prev,
          {
            peer_id: targetPeerId,
            name: peerName,
            role: peerRole,
            stream: remoteStream,
            video_enabled: true,
            audio_enabled: true
          }
        ];
      });
    };

    // If initiator, create and send SDP offer
    if (isInitiator) {
      try {
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        if (wsSignalingRef.current?.readyState === WebSocket.OPEN) {
          wsSignalingRef.current.send(JSON.stringify({
            event: 'offer',
            data: {
              target_peer_id: targetPeerId,
              signal: offer
            }
          }));
        }
      } catch (err) {
        console.error('Error creating offer:', err);
      }
    }

    return pc;
  };

  // 3. START / JOIN MEETING
  const handleStartMeeting = async (overrideRoomId, overrideMeetingId, overrideTitle) => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      return; // Prevent React rerenders from resetting active recording
    }
    setErrorMessage('');
    setVadNotice('');
    setMicStatusWarning('');

    const targetTitle = (typeof overrideTitle === 'string' ? overrideTitle : '') || meetingTitle;
    const effectiveRoomId = (typeof overrideRoomId === 'string' ? overrideRoomId : '') || roomId.trim() || `room_${Math.random().toString(36).substring(2, 10)}`;
    const targetMid = (typeof overrideMeetingId === 'string' ? overrideMeetingId : '') || currentMeetingId;

    if (!targetTitle.trim()) {
      setErrorMessage('Meeting title is required.');
      return;
    }

    if (targetMid) {
      try {
        const meetingRes = await api.get(`/meetings/room/${encodeURIComponent(effectiveRoomId)}`);
        setCurrentMeeting(meetingRes.data);
      } catch (err) {
        setErrorMessage(err.response?.data?.detail || 'Meeting not found or you do not have permission to join it.');
        setInConference(false);
        return;
      }
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      setErrorMessage('Browser does not support microphone capture (getUserMedia unavailable).');
      return;
    }

    setRoomId(effectiveRoomId);
    setMeetingTitle(targetTitle);

    const audioConstraints = {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      ...(selectedMicId ? { deviceId: { exact: selectedMicId } } : {})
    };

    // Get microphone and camera permissions
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: audioConstraints,
        video: true
      });
      localStreamRef.current = stream;
      if (localVideoRef.current) {
        localVideoRef.current.srcObject = stream;
      }
      setIsCamEnabled(true);
      setIsMicMuted(false);
      setMicPermission('granted');
      refreshAudioDevices();
    } catch (mediaErr) {
      console.warn('Camera failed, falling back to audio only:', mediaErr);
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: audioConstraints
        });
        localStreamRef.current = stream;
        setIsCamEnabled(false);
        setIsMicMuted(false);
        setMicPermission('granted');
        refreshAudioDevices();
      } catch (audioErr) {
        if (audioErr.name === 'NotAllowedError' || audioErr.name === 'PermissionDeniedError') {
          setMicPermission('denied');
          setErrorMessage('Microphone permission was denied. Please allow microphone access in your browser settings.');
        } else if (audioErr.name === 'NotFoundError' || audioErr.name === 'DevicesNotFoundError') {
          setErrorMessage('No microphone device found. Please connect a microphone and try again.');
        } else {
          setErrorMessage(`Microphone access failed: ${audioErr.message}`);
        }
        return;
      }
    }

    const audioTracks = stream.getAudioTracks();
    if (audioTracks.length === 0) {
      setErrorMessage('No active audio track captured from microphone.');
      return;
    }

    // Monitor microphone disconnection and mute state
    const primaryAudioTrack = audioTracks[0];
    primaryAudioTrack.onended = () => {
      setMicStatusWarning('Microphone disconnected during meeting!');
      setErrorMessage('Microphone disconnected. Audio capture may be incomplete.');
    };
    primaryAudioTrack.onmute = () => {
      setMicStatusWarning('Microphone hardware muted — no audio signal entering.');
    };
    primaryAudioTrack.onunmute = () => {
      setMicStatusWarning('');
    };

    // Initialize backend meeting session if not already provided
    let activeMid = targetMid;
    if (!activeMid) {
      try {
        const selectedList = activeMembers.filter((m) => selectedMemberIds.has(m.member_id));
        const res = await api.post('/meetings/start', {
          meeting_title: targetTitle.trim(),
          selected_participant_ids: Array.from(selectedMemberIds),
          participants: selectedList
        });
        activeMid = res.data.meeting_id;
        setCurrentMeeting(res.data);
        setCurrentMeetingId(activeMid);
        currentMeetingIdRef.current = activeMid;
      } catch (err) {
        console.error('Failed to initialize meeting on server:', err);
        setErrorMessage(err.response?.data?.detail || 'Unable to initialize this meeting.');
        cleanupAllMediaAndPeers();
        return;
      }
    } else {
      setCurrentMeetingId(activeMid);
      currentMeetingIdRef.current = activeMid;
    }

    // Connect WebRTC signaling
    connectSignalingWebSocket(effectiveRoomId);

    // Initialize Web Audio API mixer & real-time waveform analyser
    let recordStream = new MediaStream(audioTracks);
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (AudioContextClass) {
      try {
        const audioCtx = new AudioContextClass();
        if (audioCtx.state === 'suspended') {
          await audioCtx.resume();
        }
        audioContextRef.current = audioCtx;
        const dest = audioCtx.createMediaStreamDestination();
        audioDestinationRef.current = dest;

        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 256;
        analyserNodeRef.current = analyser;

        const localAudio = new MediaStream(audioTracks);
        const localSource = audioCtx.createMediaStreamSource(localAudio);
        localSource.connect(dest);
        localSource.connect(analyser);

        if (audioCtx.state === 'running') {
          recordStream = dest.stream;
        }

        const timeData = new Uint8Array(analyser.fftSize);
        hasDetectedSoundRef.current = false;
        silentSecondsRef.current = 0;

        const updateLevelAndWaveform = () => {
          if (!analyserNodeRef.current) return;
          analyserNodeRef.current.getByteTimeDomainData(timeData);

          let sumSq = 0;
          for (let i = 0; i < timeData.length; i++) {
            const norm = (timeData[i] - 128) / 128;
            sumSq += norm * norm;
          }
          const rms = Math.sqrt(sumSq / timeData.length);
          const level = Math.min(100, Math.round(rms * 350));
          setAudioLevel(level);
          if (level > 3) {
            hasDetectedSoundRef.current = true;
            silentSecondsRef.current = 0;
            setMicStatusWarning('');
          }

          // Draw real waveform onto canvas
          const canvas = waveformCanvasRef.current;
          if (canvas) {
            const ctx = canvas.getContext('2d');
            if (ctx) {
              const w = canvas.width;
              const h = canvas.height;
              ctx.clearRect(0, 0, w, h);
              ctx.lineWidth = 1.5;
              ctx.strokeStyle = level > 3 ? '#34D399' : '#64748B';
              ctx.beginPath();
              const sliceWidth = w / timeData.length;
              let x = 0;
              for (let i = 0; i < timeData.length; i++) {
                const v = timeData[i] / 128.0;
                const y = (v * h) / 2;
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
                x += sliceWidth;
              }
              ctx.lineTo(w, h / 2);
              ctx.stroke();
            }
          }

          animFrameRef.current = requestAnimationFrame(updateLevelAndWaveform);
        };
        updateLevelAndWaveform();
      } catch (ctxErr) {
        console.warn('AudioContext mixer failed, using direct microphone stream:', ctxErr);
        recordStream = new MediaStream(audioTracks);
      }
    }

    // Initialize MediaRecorder for complete meeting audio capture
    try {
      audioChunksRef.current = [];
      const mimeType = getSupportedMimeType();
      const recorderOptions = mimeType ? { mimeType } : undefined;
      const mediaRecorder = new MediaRecorder(recordStream, recorderOptions);
      mediaRecorderRef.current = mediaRecorder;
      recorderMimeTypeRef.current = mediaRecorder.mimeType || mimeType || 'audio/webm';

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onerror = (ev) => {
        console.error('MediaRecorder error:', ev);
        setErrorMessage('Audio recording error occurred. Please check your microphone.');
      };

      mediaRecorder.start(1000);
      setIsMeetingActive(true);
      setIsRecordingPaused(false);
      setRecordingTime(0);
      recordingTimeRef.current = 0;

      // Start recording duration timer
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = setInterval(() => {
        recordingTimeRef.current += 1;
        setRecordingTime(recordingTimeRef.current);
        if (!hasDetectedSoundRef.current && recordingTimeRef.current >= 5) {
          silentSecondsRef.current += 1;
          if (silentSecondsRef.current === 1) {
            setMicStatusWarning('No sound detected from microphone yet — check mic input or mute switch.');
          }
        }
      }, 1000);

    } catch (recErr) {
      console.error('MediaRecorder start error:', recErr);
      setErrorMessage(`Failed to start audio recorder: ${recErr.message}`);
    }
  };

  // Pause Recording
  const handlePauseRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.pause();
      setIsRecordingPaused(true);
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
        timerIntervalRef.current = null;
      }
    }
  };

  // Resume Recording
  const handleResumeRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'paused') {
      mediaRecorderRef.current.resume();
      setIsRecordingPaused(false);
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = setInterval(() => {
        recordingTimeRef.current += 1;
        setRecordingTime(recordingTimeRef.current);
      }, 1000);
    }
  };

  // Retry upload if completion encountered error
  const handleRetryUpload = async () => {
    if (!failedAudioBlob) return;
    setIsProcessing(true);
    setErrorMessage('');
    await finalizeMeetingCompletion(currentMeetingIdRef.current || currentMeetingId, failedAudioBlob, failedAudioDuration || '00:00');
  };

  // Retry Transcription (re-uses saved audio on server without re-uploading)
  const handleRetryTranscription = async () => {
    const targetMid = currentMeetingIdRef.current || currentMeetingId;
    if (!targetMid) return;
    setIsProcessing(true);
    setProcessingStep(4);
    setErrorMessage('');
    setVadNotice('');
    try {
      const res = await api.post(`/meetings/${targetMid}/retry-transcription`);
      const meetingDoc = res.data;
      setCurrentMeeting(meetingDoc);
      if (meetingDoc.status === 'failed' || meetingDoc.error_message) {
        setErrorMessage(meetingDoc.error_message || 'Transcription failed.');
      } else if (meetingDoc.vad_status === 'no_speech_detected') {
        setVadNotice(meetingDoc.vad_message || 'No clear speech was detected.');
      } else {
        setProcessingStep(8);
        const analysisRes = await api.get(`/meetings/${targetMid}/analysis`);
        setTranscripts(analysisRes.data.transcript_segments || []);
        setExtractedTasks(analysisRes.data.extracted_tasks || []);
      }
      fetchDiagnostics(targetMid);
    } catch (err) {
      setErrorMessage(err.response?.data?.detail || 'Retry transcription failed.');
    } finally {
      setIsProcessing(false);
    }
  };

  // Retry AI Analysis (re-uses saved transcript without re-uploading or re-transcribing)
  const handleRetryAnalysis = async () => {
    const targetMid = currentMeetingIdRef.current || currentMeetingId;
    if (!targetMid) return;
    setIsProcessing(true);
    setProcessingStep(6);
    setErrorMessage('');
    try {
      const res = await api.post(`/meetings/${targetMid}/retry-analysis`);
      const meetingDoc = res.data;
      setCurrentMeeting(meetingDoc);
      if (meetingDoc.status === 'failed' || meetingDoc.error_message) {
        setErrorMessage(meetingDoc.error_message || 'AI analysis failed.');
      } else {
        setProcessingStep(8);
        const analysisRes = await api.get(`/meetings/${targetMid}/analysis`);
        setTranscripts(analysisRes.data.transcript_segments || []);
        setExtractedTasks(analysisRes.data.extracted_tasks || []);
        setSidePanelTab('tasks');
      }
      fetchDiagnostics(targetMid);
    } catch (err) {
      setErrorMessage(err.response?.data?.detail || 'Retry AI analysis failed.');
    } finally {
      setIsProcessing(false);
    }
  };

  // Toggle Camera
  const handleToggleCam = () => {
    if (!localStreamRef.current) return;
    const videoTracks = localStreamRef.current.getVideoTracks();
    if (videoTracks.length > 0) {
      const nextState = !isCamEnabled;
      videoTracks.forEach((t) => (t.enabled = nextState));
      setIsCamEnabled(nextState);
      // Notify peers
      if (wsSignalingRef.current?.readyState === WebSocket.OPEN) {
        wsSignalingRef.current.send(JSON.stringify({
          event: 'track_state_changed',
          data: { video_enabled: nextState }
        }));
      }
    }
  };

  // Toggle Mic
  const handleToggleMic = () => {
    if (!localStreamRef.current) return;
    const audioTracks = localStreamRef.current.getAudioTracks();
    if (audioTracks.length > 0) {
      const nextMuted = !isMicMuted;
      audioTracks.forEach((t) => (t.enabled = !nextMuted));
      setIsMicMuted(nextMuted);
      // Notify peers
      if (wsSignalingRef.current?.readyState === WebSocket.OPEN) {
        wsSignalingRef.current.send(JSON.stringify({
          event: 'track_state_changed',
          data: { audio_enabled: !nextMuted }
        }));
      }
    }
  };

  // Toggle Screen Sharing
  const handleToggleScreenShare = async () => {
    if (isScreenSharing) {
      // Stop screen share
      if (screenTrackRef.current) {
        screenTrackRef.current.stop();
        screenTrackRef.current = null;
      }
      setIsScreenSharing(false);
      // Revert to camera track across peer connections
      const camTrack = localStreamRef.current?.getVideoTracks()[0];
      if (camTrack) {
        peersRef.current.forEach((pc) => {
          const sender = pc.getSenders().find((s) => s.track && s.track.kind === 'video');
          if (sender) sender.replaceTrack(camTrack);
        });
      }
      if (wsSignalingRef.current?.readyState === WebSocket.OPEN) {
        wsSignalingRef.current.send(JSON.stringify({
          event: 'track_state_changed',
          data: { screen_sharing: false }
        }));
      }
    } else {
      // Start screen share
      try {
        const screenStream = await navigator.mediaDevices.getDisplayMedia({ video: true });
        const screenTrack = screenStream.getVideoTracks()[0];
        screenTrackRef.current = screenTrack;
        setIsScreenSharing(true);

        // Replace track across peers
        peersRef.current.forEach((pc) => {
          const sender = pc.getSenders().find((s) => s.track && s.track.kind === 'video');
          if (sender) sender.replaceTrack(screenTrack);
        });

        screenTrack.onended = () => {
          handleToggleScreenShare();
        };

        if (wsSignalingRef.current?.readyState === WebSocket.OPEN) {
          wsSignalingRef.current.send(JSON.stringify({
            event: 'track_state_changed',
            data: { screen_sharing: true }
          }));
        }
      } catch (err) {
        console.error('Screen sharing cancelled or failed:', err);
      }
    }
  };

  // Send in-meeting chat
  const handleSendInMeetingChat = (e) => {
    e?.preventDefault();
    if (!chatInput.trim()) return;
    const text = chatInput.trim();
    setChatInput('');

    if (wsSignalingRef.current?.readyState === WebSocket.OPEN) {
      wsSignalingRef.current.send(JSON.stringify({
        event: 'meeting_chat_message',
        data: {
          sender_name: user?.name || 'You',
          text
        }
      }));
    }
  };

  // 4. END MEETING WORKFLOW
  const handleLeaveMeeting = () => {
    clearInterval(timerIntervalRef.current);
    clearInterval(chunkIntervalRef.current);
    if (wsSignalingRef.current?.readyState === WebSocket.OPEN) {
      wsSignalingRef.current.send(JSON.stringify({ event: 'leave_room', data: {} }));
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.onstop = null;
      mediaRecorderRef.current.stop();
    }
    cleanupAllMediaAndPeers();
    setIsMeetingActive(false);
    setIsProcessing(false);
    setInConference(false);
  };

  const handleEndMeeting = async () => {
    if (!isMeetingHost) {
      handleLeaveMeeting();
      return;
    }

    clearInterval(timerIntervalRef.current);
    clearInterval(chunkIntervalRef.current);
    setIsMeetingActive(false);
    setIsProcessing(true);
    setProcessingStep(1);

    const activeMid = currentMeetingIdRef.current || currentMeetingId;
    const capturedDuration = formatTimer(recordingTimeRef.current || recordingTime);

    if (currentMeeting?.scheduled_start_at && activeMid) {
      try {
        await api.post(`/meetings/${activeMid}/end-session`);
      } catch (err) {
        setErrorMessage(err.response?.data?.detail || 'Only the meeting host can end this scheduled meeting.');
        setIsProcessing(false);
        return;
      }
    }

    // Signal meeting ended to peers if host
    if (wsSignalingRef.current?.readyState === WebSocket.OPEN) {
      wsSignalingRef.current.send(JSON.stringify({
        event: 'end_meeting',
        data: { ended_by: user?.name || 'Team Leader' }
      }));
    }

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try {
        mediaRecorderRef.current.onstop = async () => {
          cleanupAllMediaAndPeers();

          if (audioChunksRef.current.length === 0) {
            setErrorMessage('No audio data captured during meeting session. Please check microphone.');
            setIsProcessing(false);
            return;
          }

          const mime = recorderMimeTypeRef.current || 'audio/webm';
          const completeBlob = new Blob(audioChunksRef.current, { type: mime });
          if (completeBlob.size < 100) {
            setErrorMessage('Captured audio is empty or too short. Please check microphone.');
            setIsProcessing(false);
            return;
          }
          await finalizeMeetingCompletion(activeMid, completeBlob, capturedDuration);
        };
        mediaRecorderRef.current.requestData?.();
        mediaRecorderRef.current.stop();
      } catch (err) {
        console.error('Error stopping recorder:', err);
        cleanupAllMediaAndPeers();
        setIsProcessing(false);
      }
    } else {
      cleanupAllMediaAndPeers();
      setIsProcessing(false);
    }
  };

  const finalizeMeetingCompletion = async (meetingId, audioBlob, durationStr) => {
    try {
      setProcessingStep(2); // Uploading audio
      const ext = getExtensionForMime(audioBlob.type || recorderMimeTypeRef.current);
      const formData = new FormData();
      formData.append('file', audioBlob, `meeting_${meetingId || 'session'}.${ext}`);
      formData.append('duration', durationStr || '00:00');

      const targetMid = meetingId || 'session';
      setProcessingStep(3); // Validating audio & running backend pipeline
      const completeRes = await api.post(`/meetings/${targetMid}/complete`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      const meetingDoc = completeRes.data;
      setCurrentMeeting(meetingDoc);

      if (meetingDoc.status === 'failed' || meetingDoc.error_message) {
        setErrorMessage(meetingDoc.error_message || 'Meeting processing failed.');
        setFailedAudioBlob(audioBlob);
        setFailedAudioDuration(durationStr);
        fetchDiagnostics(targetMid);
        return;
      }

      if (meetingDoc.vad_status === 'no_speech_detected') {
        setVadNotice(meetingDoc.vad_message || 'No clear speech was detected. Please check your microphone and try again.');
        fetchDiagnostics(targetMid);
        return;
      }

      setProcessingStep(8); // Ready for review ONLY after actual completion
      const analysisRes = await api.get(`/meetings/${targetMid}/analysis`);
      setTranscripts(analysisRes.data.transcript_segments || []);
      setExtractedTasks(analysisRes.data.extracted_tasks || []);
      setSidePanelTab('tasks');
      setIsSidePanelOpen(true);
      setFailedAudioBlob(null);
      setFailedAudioDuration('');
      fetchDiagnostics(targetMid);
    } catch (err) {
      console.error('Failed to complete meeting workflow:', err);
      setFailedAudioBlob(audioBlob);
      setFailedAudioDuration(durationStr);
      setErrorMessage(err.response?.data?.detail || 'Multi-agent analysis encountered an error. Click "Retry Upload" to re-process.');
    } finally {
      setIsProcessing(false);
    }
  };

  // Task Editing & Approval
  const handleStartEditTask = (task) => {
    setEditingTask({ ...task });
  };

  const handleSaveTaskEdit = () => {
    if (!editingTask) return;
    setExtractedTasks((prev) =>
      prev.map((t) => (t.task_id === editingTask.task_id ? { ...editingTask } : t))
    );
    setEditingTask(null);
  };

  const handleCancelEditTask = () => {
    setEditingTask(null);
  };

  // Task Approval & Save (Human-in-the-loop review)
  const handleApproveTask = async (taskId, currentTask) => {
    try {
      const taskToApprove = editingTask?.task_id === taskId ? editingTask : (currentTask || extractedTasks.find(t => t.task_id === taskId));
      const payload = {
        task_id: taskId,
        priority: taskToApprove?.priority || 'Medium',
        deadline: taskToApprove?.deadline,
        assigned_member_id: taskToApprove?.assigned_member_id,
        assigned_member_name: taskToApprove?.assigned_member_name || 'Unassigned',
        assigned_member_email: taskToApprove?.assigned_member_email,
        assigned_member_role: taskToApprove?.assigned_member_role
      };

      if (currentMeetingId) {
        await api.post(`/meetings/${currentMeetingId}/tasks/approve`, payload);
      } else {
        await api.post(`/tasks/${taskId}/approve`);
      }

      setApprovedTaskIds((prev) => new Set([...prev, taskId]));
    } catch (err) {
      alert('Failed to approve task: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleRejectTask = async (taskId) => {
    try {
      await api.post(`/tasks/${taskId}/reject`);
      setRejectedTaskIds((prev) => new Set([...prev, taskId]));
    } catch (err) {
      alert('Failed to reject task: ' + (err.response?.data?.detail || err.message));
    }
  };

  const getInitials = (name) => {
    if (!name) return 'MM';
    return name.split(' ').map((n) => n[0]).join('').toUpperCase().substring(0, 2);
  };

  return (
    <div className="space-y-4 animate-fade-in pb-12">
      {!inConference ? (
        /* ==================== GOOGLE MEET-STYLE LANDING HUB ==================== */
        <div className="space-y-8 max-w-6xl mx-auto py-2">
          
          {/* Top Bar: MeetMind Logo, Live Clock, and Host Profile Pill */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#E2E8F0]">
            <div>
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-[#1A73E8] to-[#4285F4] text-white flex items-center justify-center shadow-sm">
                  <Video className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-xl font-bold text-[#0F172A] tracking-tight">MeetMind Conference Hub</h2>
                  <p className="text-xs text-[#64748B]">Google Meet-Style Schedule-First Meeting Workspace</p>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {/* Live Clock & Date */}
              <div className="text-right hidden sm:block">
                <div className="text-xs font-semibold text-[#0F172A]">
                  {currentTime.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}
                </div>
                <div className="text-xs text-[#64748B] font-mono">
                  {currentTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </div>
              </div>

              <div className="h-6 w-px bg-[#E2E8F0] hidden sm:block" />

              {/* Signed-in workspace role */}
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1]">
                <div className="w-7 h-7 rounded-full bg-[#1A73E8] text-white flex items-center justify-center text-xs font-bold shadow-xs">
                  {getInitials(user?.name || 'You')}
                </div>
                <div className="text-left">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-bold text-[#0F172A]">{user?.name || 'You'}</span>
                    <span className={`px-1.5 py-0.2 rounded text-white font-extrabold text-[8px] uppercase tracking-wider ${isLeader ? 'bg-blue-600' : 'bg-slate-500'}`}>
                      {isLeader ? 'TEAM LEADER' : 'TEAM MEMBER'}
                    </span>
                  </div>
                  <span className="text-[10px] text-[#64748B] block truncate max-w-[120px]">{user?.email || 'Logged In'}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Success / Error Alerts */}
          {scheduleResult && (
            <div className="p-3.5 rounded-xl bg-white border border-[#CBD5E1] text-xs space-y-2 shadow-xs animate-fade-in">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-emerald-900">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                  <span className="font-medium">Meeting saved: {scheduleResult.meeting_title} ({scheduleResult.meeting_id})</span>
                </div>
                <button onClick={() => setScheduleResult(null)} className="p-1 hover:bg-slate-100 rounded text-slate-600 cursor-pointer">
                  <X className="w-3.5 h-3.5" />
                </button>
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

          {errorMessage && (
            <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center justify-between shadow-xs">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>{errorMessage}</span>
              </div>
              <button onClick={() => setErrorMessage('')} className="p-1 hover:bg-rose-100 rounded text-rose-600 cursor-pointer">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {/* Google Meet Hero Section */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center py-2">
            
            {/* Left Hero: Headline & Actions */}
            <div className="lg:col-span-7 space-y-6">
              <div className="space-y-3">
                <h1 className="text-3xl sm:text-4xl font-extrabold text-[#0F172A] tracking-tight leading-tight">
                  Video calls and meetings for everyone.
                </h1>
                <p className="text-sm sm:text-base text-[#475569] leading-relaxed max-w-xl">
                  Connect, collaborate, and extract intelligent deliverables with MeetMind AI. Schedule ahead, launch instant meetings, or join with a room code.
                </p>
              </div>

              {/* Action Buttons: New Meeting Dropdown, Schedule Meeting, and Join Code Input */}
              <div className="flex flex-wrap items-center gap-3 pt-2">
                
                {isLeader && (
                <>
                {/* New Meeting Dropdown */}
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setIsNewMeetingDropdownOpen(!isNewMeetingDropdownOpen)}
                    className="flex items-center gap-2 px-5 py-3 rounded-full bg-[#1A73E8] hover:bg-[#1557B0] text-white text-xs sm:text-sm font-bold shadow-md transition cursor-pointer"
                  >
                    <Video className="w-4 h-4" />
                    <span>New Meeting</span>
                    <ChevronDown className="w-3.5 h-3.5" />
                  </button>

                  {isNewMeetingDropdownOpen && (
                    <div className="absolute left-0 mt-2 w-64 rounded-2xl bg-white border border-[#E2E8F0] shadow-xl py-2 z-30 animate-fade-in text-xs">
                      <button
                        onClick={handleCreateMeetingForLater}
                        className="w-full text-left px-4 py-2.5 hover:bg-[#F8FAFC] flex items-center gap-3 text-[#0F172A] transition cursor-pointer"
                      >
                        <Link2 className="w-4 h-4 text-[#2563EB]" />
                        <div>
                          <div className="font-bold">Create a meeting for later</div>
                          <div className="text-[10px] text-[#64748B]">Get a link you can share</div>
                        </div>
                      </button>

                      <button
                        onClick={handleStartInstantMeeting}
                        className="w-full text-left px-4 py-2.5 hover:bg-[#F8FAFC] flex items-center gap-3 text-[#0F172A] transition border-t border-[#F1F5F9] cursor-pointer"
                      >
                        <Plus className="w-4 h-4 text-[#10B981]" />
                        <div>
                          <div className="font-bold">Start an instant meeting</div>
                          <div className="text-[10px] text-[#64748B]">Open room immediately as Host</div>
                        </div>
                      </button>

                      <button
                        onClick={() => {
                          setIsNewMeetingDropdownOpen(false);
                          setShowScheduleModal(true);
                        }}
                        className="w-full text-left px-4 py-2.5 hover:bg-[#F8FAFC] flex items-center gap-3 text-[#0F172A] transition border-t border-[#F1F5F9] cursor-pointer"
                      >
                        <CalendarClock className="w-4 h-4 text-[#7C3AED]" />
                        <div>
                          <div className="font-bold">Schedule a meeting</div>
                          <div className="text-[10px] text-[#64748B]">Plan date, time & invite team</div>
                        </div>
                      </button>
                    </div>
                  )}
                </div>

                {/* Direct Schedule Button */}
                <button
                  type="button"
                  onClick={() => setShowScheduleModal(true)}
                  className="flex items-center gap-2 px-4 py-3 rounded-full bg-white hover:bg-[#F8FAFC] border border-[#CBD5E1] text-[#0F172A] text-xs sm:text-sm font-semibold shadow-xs transition cursor-pointer"
                >
                  <CalendarClock className="w-4 h-4 text-[#2563EB]" />
                  <span>Schedule a Meeting</span>
                </button>
                </>
                )}

                {/* Join with a Meeting Code Form */}
                <form onSubmit={handleJoinWithCode} className="flex items-center gap-2">
                  <div className="relative flex items-center">
                    <Keyboard className="w-4 h-4 text-[#94A3B8] absolute left-3.5 pointer-events-none" />
                    <input
                      type="text"
                      value={codeOrLinkInput}
                      onChange={(e) => setCodeOrLinkInput(e.target.value)}
                      placeholder="Enter code or link"
                      className="pl-10 pr-3 py-2.5 rounded-full bg-white border border-[#CBD5E1] focus:border-[#1A73E8] focus:ring-1 focus:ring-[#1A73E8] text-xs sm:text-sm text-[#0F172A] outline-none w-44 sm:w-52 transition font-mono"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={!codeOrLinkInput.trim()}
                    className={`px-4 py-2.5 rounded-full text-xs sm:text-sm font-bold transition shadow-xs ${
                      codeOrLinkInput.trim()
                        ? 'bg-[#1A73E8] hover:bg-[#1557B0] text-white cursor-pointer'
                        : 'bg-[#E2E8F0] text-[#94A3B8] cursor-not-allowed'
                    }`}
                  >
                    Join
                  </button>
                </form>

              </div>

              {/* Single Member Workspace Notice */}
              {activeMembers.length <= 1 && (
                <div className="p-3 rounded-xl bg-blue-50/70 border border-blue-200 text-blue-900 text-xs flex items-center gap-2">
                  <Info className="w-4 h-4 text-blue-600 flex-shrink-0" />
                  <span>
                    <strong>Solo Workspace:</strong> You can schedule meetings and start recordings as host without needing other members.
                  </span>
                </div>
              )}
            </div>

            {/* Right Hero: Google Meet Security & Next Up Card */}
            <div className="lg:col-span-5">
              <div className="rounded-3xl bg-gradient-to-br from-[#F8FAFC] to-[#EFF6FF] border border-[#E2E8F0] p-6 shadow-sm space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center">
                      <ShieldCheck className="w-4 h-4" />
                    </div>
                    <span className="text-xs font-bold text-[#0F172A]">Enterprise Privacy</span>
                  </div>
                  <span className="text-[10px] px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-800 font-bold">
                    WebRTC Mesh Active
                  </span>
                </div>

                <p className="text-xs text-[#475569] leading-relaxed">
                  Calls are peer-to-peer encrypted through WebRTC STUN signaling. Audio recordings and multi-agent AI deliverables remain confined to your MongoDB Atlas team workspace.
                </p>

                {/* Quick Next Upcoming Meeting Preview */}
                {upcomingMeetings.length > 0 && (
                  <div className="p-4 rounded-2xl bg-white border border-[#BFDBFE] space-y-2.5 shadow-xs">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-[#2563EB]">Next Scheduled Call</span>
                      <span className="text-[11px] font-mono text-[#64748B]">{upcomingMeetings[0].time_until_start_seconds > 0 ? `Starts soon` : 'Joinable now'}</span>
                    </div>
                    <h4 className="font-bold text-xs text-[#0F172A] truncate">{upcomingMeetings[0].meeting_title}</h4>
                    <div className="flex items-center justify-between pt-1">
                      <span className="text-[11px] text-[#64748B]">Room: <code className="font-mono text-[#0F172A]">{upcomingMeetings[0].room_id}</code></span>
                      <button
                        onClick={() => isMeetingHostUser(upcomingMeetings[0]) && !['active', 'live'].includes(upcomingMeetings[0].meeting_status)
                          ? handleStartScheduledMeeting(upcomingMeetings[0])
                          : handleJoinScheduledMeeting(upcomingMeetings[0])}
                        className="px-3 py-1.5 rounded-lg bg-[#1A73E8] hover:bg-[#1557B0] text-white text-xs font-bold shadow-xs cursor-pointer flex items-center gap-1"
                      >
                        <Play className="w-3 h-3 fill-current" />
                        <span>{isMeetingHostUser(upcomingMeetings[0]) && !['active', 'live'].includes(upcomingMeetings[0].meeting_status) ? 'Start Call' : 'Join Call'}</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>

          </div>

          {/* Tab Navigation: Upcoming Meetings vs Recent Meetings */}
          <div className="space-y-4 pt-4">
            <div className="flex items-center justify-between border-b border-[#E2E8F0]">
              <div className="flex items-center gap-4">
                <button
                  type="button"
                  onClick={() => setHubTab('upcoming')}
                  className={`pb-3 text-xs sm:text-sm font-bold transition flex items-center gap-2 cursor-pointer border-b-2 ${
                    hubTab === 'upcoming'
                      ? 'border-[#1A73E8] text-[#1A73E8]'
                      : 'border-transparent text-[#64748B] hover:text-[#0F172A]'
                  }`}
                >
                  <CalendarClock className="w-4 h-4" />
                  <span>Upcoming Meetings</span>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#EFF6FF] text-[#1A73E8]">
                    {upcomingMeetings.length}
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => setHubTab('recent')}
                  className={`pb-3 text-xs sm:text-sm font-bold transition flex items-center gap-2 cursor-pointer border-b-2 ${
                    hubTab === 'recent'
                      ? 'border-[#1A73E8] text-[#1A73E8]'
                      : 'border-transparent text-[#64748B] hover:text-[#0F172A]'
                  }`}
                >
                  <Clock className="w-4 h-4" />
                  <span>Recent Meetings</span>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#F1F5F9] text-[#64748B]">
                    {recentMeetings.length}
                  </span>
                </button>
              </div>

              <button
                onClick={() => {
                  fetchUpcomingMeetings();
                  fetchRecentMeetings();
                }}
                className="text-xs text-[#2563EB] hover:underline flex items-center gap-1 pb-3 cursor-pointer"
              >
                <RotateCcw className="w-3 h-3" />
                <span>Refresh</span>
              </button>
            </div>

            {/* TAB 1: UPCOMING MEETINGS */}
            {hubTab === 'upcoming' && (
              <div className="space-y-3">
                {isLoadingUpcoming ? (
                  <div className="p-12 text-center text-xs text-[#64748B] space-y-2">
                    <Cpu className="w-6 h-6 animate-spin text-[#2563EB] mx-auto" />
                    <p>Loading scheduled meetings from MongoDB Atlas...</p>
                  </div>
                ) : upcomingMeetings.length === 0 ? (
                  <div className="p-12 rounded-2xl bg-white border border-dashed border-[#CBD5E1] text-center space-y-3">
                    <div className="w-12 h-12 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center mx-auto">
                      <CalendarClock className="w-6 h-6" />
                    </div>
                    <div className="space-y-1">
                      <h4 className="text-sm font-bold text-[#0F172A]">No upcoming meetings</h4>
                      <p className="text-xs text-[#64748B]">Schedule a meeting or start an instant meeting to collaborate with teammates.</p>
                    </div>
                    {isLeader && (
                      <button
                        onClick={() => setShowScheduleModal(true)}
                        className="px-4 py-2 rounded-xl bg-[#1A73E8] hover:bg-[#1557B0] text-white text-xs font-bold transition shadow-xs cursor-pointer inline-flex items-center gap-1.5"
                      >
                        <Plus className="w-3.5 h-3.5" />
                        <span>Schedule a Meeting</span>
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {upcomingMeetings.map((m) => {
                      const isHost = isMeetingHostUser(m);
                      const isLive = m.meeting_status === 'active' || m.meeting_status === 'live';

                      return (
                        <div key={m.meeting_id} className="p-4 rounded-2xl bg-white border border-[#E2E8F0] shadow-xs hover:shadow-md transition space-y-3 flex flex-col justify-between">
                          <div className="space-y-2">
                            <div className="flex items-start justify-between gap-2">
                              <div>
                                <span className="font-mono text-[10px] text-[#2563EB] font-bold block">{m.meeting_id}</span>
                                <h4 className="font-bold text-sm text-[#0F172A] leading-snug">{m.meeting_title}</h4>
                              </div>
                              <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md border flex items-center gap-1 ${
                                isLive
                                  ? 'bg-emerald-50 text-emerald-700 border-emerald-300 animate-pulse'
                                  : 'bg-blue-50 text-blue-700 border-blue-200'
                              }`}>
                                {isLive && <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping" />}
                                <span>{isLive ? 'LIVE' : 'SCHEDULED'}</span>
                              </span>
                            </div>

                            <div className="space-y-1 text-xs text-[#64748B]">
                              <div className="flex items-center gap-1.5">
                                <Clock className="w-3.5 h-3.5 text-[#94A3B8]" />
                                <span>{new Date(m.scheduled_start_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} at {new Date(m.scheduled_start_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                              </div>
                              <div className="flex items-center gap-1.5">
                                <Users className="w-3.5 h-3.5 text-[#94A3B8]" />
                                <span>{m.participants?.length || 1} participant{m.participants?.length === 1 ? '' : 's'}</span>
                              </div>
                              <div className="text-[11px]">Host: <span className="font-semibold text-[#0F172A]">{m.host_name || 'Team Leader'}</span></div>
                            </div>
                          </div>

                          <div className="space-y-2 pt-2 border-t border-[#F1F5F9]">
                            <div className="flex items-center gap-2">
                              {isHost && !isLive ? (
                                <button
                                  onClick={() => handleStartScheduledMeeting(m)}
                                  className="flex-1 py-2 rounded-xl bg-[#1A73E8] hover:bg-[#1557B0] text-white text-xs font-bold shadow-xs transition cursor-pointer flex items-center justify-center gap-1.5"
                                >
                                  <Video className="w-3.5 h-3.5" />
                                  <span>{isMeetingHost ? 'Start Meeting' : 'Join Meeting'}</span>
                                </button>
                              ) : (
                                <button
                                  onClick={() => handleJoinScheduledMeeting(m)}
                                  className="flex-1 py-2 rounded-xl bg-[#059669] hover:bg-[#047857] text-white text-xs font-bold shadow-xs transition cursor-pointer flex items-center justify-center gap-1.5"
                                >
                                  <Radio className="w-3.5 h-3.5" />
                                  <span>Join Call</span>
                                </button>
                              )}

                              <button
                                onClick={() => handleViewDetails(m)}
                                title="View Details"
                                className="p-2 rounded-xl border border-[#CBD5E1] hover:bg-[#F8FAFC] text-[#475569] cursor-pointer"
                              >
                                <Eye className="w-3.5 h-3.5" />
                              </button>

                              {isHost && (
                                <>
                                  <button
                                    onClick={() => handleEditMeeting(m)}
                                    title="Edit Meeting"
                                    className="p-2 rounded-xl border border-[#CBD5E1] hover:bg-[#F8FAFC] text-[#475569] cursor-pointer"
                                  >
                                    <Edit3 className="w-3.5 h-3.5" />
                                  </button>

                                  <button
                                    onClick={() => handleCancelScheduledMeeting(m.meeting_id)}
                                    title="Cancel Meeting"
                                    className="p-2 rounded-xl border border-[#CBD5E1] hover:bg-rose-50 text-rose-600 cursor-pointer"
                                  >
                                    <Trash2 className="w-3.5 h-3.5" />
                                  </button>
                                </>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* TAB 2: RECENT MEETINGS */}
            {hubTab === 'recent' && (
              <div className="space-y-3">
                {isLoadingRecent ? (
                  <div className="p-12 text-center text-xs text-[#64748B]">Loading completed meetings...</div>
                ) : recentMeetings.length === 0 ? (
                  <div className="p-12 rounded-2xl bg-white border border-dashed border-[#CBD5E1] text-center space-y-2">
                    <Clock className="w-6 h-6 text-[#94A3B8] mx-auto" />
                    <p className="text-xs text-[#64748B]">No completed meetings found in MongoDB history.</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {recentMeetings.map((m) => (
                      <div key={m.meeting_id} className="p-4 rounded-2xl bg-white border border-[#E2E8F0] shadow-xs space-y-3 flex flex-col justify-between">
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between">
                            <span className="font-mono text-[10px] text-[#2563EB] font-bold">{m.meeting_id}</span>
                            <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 font-bold border border-emerald-200">
                              COMPLETED
                            </span>
                          </div>
                          <h4 className="font-bold text-xs text-[#0F172A] truncate">{m.meeting_title || m.title}</h4>
                          <p className="text-[11px] text-[#64748B] line-clamp-2">
                            {m.meeting_summary || m.summary || 'Meeting processed with LangGraph AI analytics.'}
                          </p>
                        </div>

                        <div className="flex items-center justify-between pt-2 border-t border-[#F1F5F9]">
                          <span className="text-[10px] text-[#94A3B8]">Duration: {m.duration || 'N/A'}</span>
                          <button
                            onClick={() => window.open(`${api.defaults.baseURL}/meetings/${m.meeting_id}/export-pdf`, '_blank')}
                            className="px-2.5 py-1 rounded-lg bg-white border border-[#CBD5E1] hover:bg-[#F8FAFC] text-[11px] font-semibold text-[#2563EB] flex items-center gap-1 cursor-pointer"
                          >
                            <Download className="w-3.5 h-3.5" />
                            <span>PDF</span>
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

          </div>

          {/* SCHEDULE MEETING MODAL */}
          {showScheduleModal && isLeader && (
            <div className="fixed inset-0 bg-black/50 backdrop-blur-xs flex items-center justify-center z-50 p-4 animate-fade-in">
              <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-[#E2E8F0] space-y-4 max-h-[90vh] overflow-y-auto">
                <div className="flex items-center justify-between pb-3 border-b border-[#E2E8F0]">
                  <div className="flex items-center gap-2">
                    <CalendarClock className="w-5 h-5 text-[#2563EB]" />
                    <h3 className="font-bold text-base text-[#0F172A]">Schedule a Meeting</h3>
                  </div>
                  <button onClick={() => setShowScheduleModal(false)} className="p-1 hover:bg-[#F1F5F9] rounded text-[#64748B] cursor-pointer">
                    <X className="w-4 h-4" />
                  </button>
                </div>

                <form onSubmit={handleScheduleFormSubmit} className="space-y-3.5 text-xs">
                  <div>
                    <label className="block font-semibold text-[#475569] mb-1">Meeting Title *</label>
                    <input
                      type="text"
                      required
                      value={scheduleForm.meeting_title}
                      onChange={(e) => setScheduleForm({ ...scheduleForm, meeting_title: e.target.value })}
                      placeholder="e.g. Q1 Product Architecture Sync"
                      className="w-full px-3 py-2 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1] font-semibold text-[#0F172A] outline-none focus:border-[#2563EB]"
                    />
                  </div>

                  <div>
                    <label className="block font-semibold text-[#475569] mb-1">Description / Agenda</label>
                    <textarea
                      rows={2}
                      value={scheduleForm.description}
                      onChange={(e) => setScheduleForm({ ...scheduleForm, description: e.target.value })}
                      placeholder="Discuss deliverables, review sprint goals, and assign action items."
                      className="w-full px-3 py-2 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1] text-[#0F172A] outline-none focus:border-[#2563EB]"
                    />
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                    <div>
                      <label className="block font-semibold text-[#475569] mb-1">Date *</label>
                      <input
                        type="date"
                        required
                        value={scheduleForm.date}
                        onChange={(e) => setScheduleForm({ ...scheduleForm, date: e.target.value })}
                        className="w-full px-2.5 py-1.5 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1] text-[#0F172A]"
                      />
                    </div>
                    <div>
                      <label className="block font-semibold text-[#475569] mb-1">Start Time *</label>
                      <input
                        type="time"
                        required
                        value={scheduleForm.time}
                        onChange={(e) => setScheduleForm({ ...scheduleForm, time: e.target.value })}
                        className="w-full px-2.5 py-1.5 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1] text-[#0F172A]"
                      />
                    </div>
                    <div>
                      <label className="block font-semibold text-[#475569] mb-1">Duration</label>
                      <select
                        value={scheduleForm.duration_minutes}
                        onChange={(e) => setScheduleForm({ ...scheduleForm, duration_minutes: Number(e.target.value) })}
                        className="w-full px-2.5 py-1.5 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1] text-[#0F172A]"
                      >
                        <option value={15}>15 mins</option>
                        <option value={30}>30 mins</option>
                        <option value={45}>45 mins</option>
                        <option value={60}>60 mins</option>
                        <option value={90}>90 mins</option>
                      </select>
                    </div>
                  </div>

                  <div>
                    <label className="block font-semibold text-[#475569] mb-1">
                      Workspace Participants ({scheduleForm.selected_participant_ids.length} selected)
                    </label>
                    {activeMembers.length > 0 ? (
                      <div className="max-h-36 overflow-y-auto space-y-1 p-2 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1]">
                        {activeMembers.map((m) => {
                          const isChecked = scheduleForm.selected_participant_ids.includes(m.member_id);
                          return (
                            <label key={m.member_id} className="flex items-center gap-2 p-1.5 rounded hover:bg-white cursor-pointer transition">
                              <input
                                type="checkbox"
                                checked={isChecked}
                                onChange={(e) => {
                                  if (e.target.checked) {
                                    setScheduleForm({
                                      ...scheduleForm,
                                      selected_participant_ids: [...scheduleForm.selected_participant_ids, m.member_id]
                                    });
                                  } else {
                                    setScheduleForm({
                                      ...scheduleForm,
                                      selected_participant_ids: scheduleForm.selected_participant_ids.filter(id => id !== m.member_id)
                                    });
                                  }
                                }}
                                className="rounded text-[#2563EB]"
                              />
                              <div className="flex-1 truncate">
                                <span className="font-semibold text-[#0F172A] mr-1">{m.name}</span>
                                <span className="text-[10px] text-[#64748B]">({m.role || 'Member'})</span>
                              </div>
                            </label>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="p-3 rounded-xl bg-blue-50 text-blue-900 text-xs">
                        Host only (Solo Workspace): You will be registered as host automatically.
                      </div>
                    )}
                  </div>

                  <div className="flex items-center justify-end gap-2 pt-3 border-t border-[#E2E8F0]">
                    <button
                      type="button"
                      onClick={() => setShowScheduleModal(false)}
                      className="px-4 py-2 rounded-xl border border-[#CBD5E1] text-[#475569] hover:bg-[#F8FAFC] font-semibold cursor-pointer"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isSubmittingSchedule}
                      className="px-5 py-2 rounded-xl bg-[#1A73E8] hover:bg-[#1557B0] text-white font-bold shadow-xs cursor-pointer disabled:opacity-50"
                    >
                      {isSubmittingSchedule ? 'Scheduling in MongoDB...' : 'Confirm & Schedule'}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}

          {/* EDIT MEETING MODAL */}
          {showEditModal && selectedMeeting && isMeetingHostUser(selectedMeeting) && (
            <div className="fixed inset-0 bg-black/50 backdrop-blur-xs flex items-center justify-center z-50 p-4 animate-fade-in">
              <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-[#E2E8F0] space-y-4 max-h-[90vh] overflow-y-auto">
                <div className="flex items-center justify-between pb-3 border-b border-[#E2E8F0]">
                  <div className="flex items-center gap-2">
                    <Edit3 className="w-5 h-5 text-[#2563EB]" />
                    <h3 className="font-bold text-base text-[#0F172A]">Edit Scheduled Meeting</h3>
                  </div>
                  <button onClick={() => setShowEditModal(false)} className="p-1 hover:bg-[#F1F5F9] rounded text-[#64748B] cursor-pointer">
                    <X className="w-4 h-4" />
                  </button>
                </div>

                <form onSubmit={handleEditFormSubmit} className="space-y-3.5 text-xs">
                  <div>
                    <label className="block font-semibold text-[#475569] mb-1">Meeting Title</label>
                    <input
                      type="text"
                      required
                      value={scheduleForm.meeting_title}
                      onChange={(e) => setScheduleForm({ ...scheduleForm, meeting_title: e.target.value })}
                      className="w-full px-3 py-2 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1] font-semibold text-[#0F172A]"
                    />
                  </div>

                  <div>
                    <label className="block font-semibold text-[#475569] mb-1">Description / Agenda</label>
                    <textarea
                      rows={2}
                      value={scheduleForm.description}
                      onChange={(e) => setScheduleForm({ ...scheduleForm, description: e.target.value })}
                      className="w-full px-3 py-2 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1] text-[#0F172A]"
                    />
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                    <div>
                      <label className="block font-semibold text-[#475569] mb-1">Date</label>
                      <input
                        type="date"
                        required
                        value={scheduleForm.date}
                        onChange={(e) => setScheduleForm({ ...scheduleForm, date: e.target.value })}
                        className="w-full px-2.5 py-1.5 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1]"
                      />
                    </div>
                    <div>
                      <label className="block font-semibold text-[#475569] mb-1">Time</label>
                      <input
                        type="time"
                        required
                        value={scheduleForm.time}
                        onChange={(e) => setScheduleForm({ ...scheduleForm, time: e.target.value })}
                        className="w-full px-2.5 py-1.5 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1]"
                      />
                    </div>
                    <div>
                      <label className="block font-semibold text-[#475569] mb-1">Duration</label>
                      <select
                        value={scheduleForm.duration_minutes}
                        onChange={(e) => setScheduleForm({ ...scheduleForm, duration_minutes: Number(e.target.value) })}
                        className="w-full px-2.5 py-1.5 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1]"
                      >
                        <option value={15}>15 mins</option>
                        <option value={30}>30 mins</option>
                        <option value={45}>45 mins</option>
                        <option value={60}>60 mins</option>
                      </select>
                    </div>
                  </div>

                  <div className="flex items-center justify-end gap-2 pt-3 border-t border-[#E2E8F0]">
                    <button
                      type="button"
                      onClick={() => setShowEditModal(false)}
                      className="px-4 py-2 rounded-xl border border-[#CBD5E1] text-[#475569] cursor-pointer"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      className="px-5 py-2 rounded-xl bg-[#1A73E8] hover:bg-[#1557B0] text-white font-bold cursor-pointer"
                    >
                      Save Changes
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}

          {/* MEETING DETAILS MODAL */}
          {showDetailsModal && selectedMeeting && (
            <div className="fixed inset-0 bg-black/50 backdrop-blur-xs flex items-center justify-center z-50 p-4 animate-fade-in">
              <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-[#E2E8F0] space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-[#E2E8F0]">
                  <div>
                    <span className="font-mono text-[10px] text-[#2563EB] font-bold">{selectedMeeting.meeting_id}</span>
                    <h3 className="font-bold text-base text-[#0F172A]">{selectedMeeting.meeting_title}</h3>
                  </div>
                  <button onClick={() => setShowDetailsModal(false)} className="p-1 hover:bg-[#F1F5F9] rounded text-[#64748B] cursor-pointer">
                    <X className="w-4 h-4" />
                  </button>
                </div>

                <div className="space-y-3 text-xs text-[#475569]">
                  <div>
                    <strong className="text-[#0F172A] block mb-0.5">Description / Agenda:</strong>
                    <p className="p-2.5 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] leading-relaxed">
                      {selectedMeeting.description || selectedMeeting.agenda || 'No agenda specified.'}
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <strong className="text-[#0F172A] block">Date & Time:</strong>
                      <span>{new Date(selectedMeeting.scheduled_start_at).toLocaleString()}</span>
                    </div>
                    <div>
                      <strong className="text-[#0F172A] block">Duration:</strong>
                      <span>{selectedMeeting.duration_minutes || 30} mins</span>
                    </div>
                  </div>

                  <div>
                    <strong className="text-[#0F172A] block mb-1">Room Link:</strong>
                    <div className="flex items-center gap-2 p-2 rounded-xl bg-black/5 border border-[#CBD5E1]">
                      <span className="font-mono text-[11px] truncate flex-1">{window.location.origin}/live-meeting?room={selectedMeeting.room_id}&title={encodeURIComponent(selectedMeeting.meeting_title)}</span>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(`${window.location.origin}/live-meeting?room=${selectedMeeting.room_id}&title=${encodeURIComponent(selectedMeeting.meeting_title)}`);
                          alert('Meeting link copied to clipboard!');
                        }}
                        className="px-2.5 py-1 rounded bg-[#2563EB] text-white text-[11px] font-bold cursor-pointer"
                      >
                        Copy
                      </button>
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-end pt-3 border-t border-[#E2E8F0]">
                  <button
                    onClick={() => setShowDetailsModal(false)}
                    className="px-4 py-2 rounded-xl bg-[#F1F5F9] text-[#0F172A] text-xs font-semibold cursor-pointer"
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* CREATE MEETING FOR LATER LINK MODAL */}
          {showLaterLinkModal && createdLaterMeeting && (
            <div className="fixed inset-0 bg-black/50 backdrop-blur-xs flex items-center justify-center z-50 p-4 animate-fade-in">
              <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-[#E2E8F0] space-y-4">
                <div className="flex items-center justify-between pb-2 border-b border-[#E2E8F0]">
                  <h3 className="font-bold text-sm text-[#0F172A]">Here's the link to your meeting</h3>
                  <button onClick={() => setShowLaterLinkModal(false)} className="p-1 hover:bg-[#F1F5F9] rounded text-[#64748B] cursor-pointer">
                    <X className="w-4 h-4" />
                  </button>
                </div>

                <p className="text-xs text-[#64748B] leading-relaxed">
                  Copy this link and send it to people you want to meet with. Be sure to save it so you can use it later, too.
                </p>

                <div className="flex items-center gap-2 p-2.5 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1]">
                  <a
                    className="font-mono text-xs text-[#2563EB] underline truncate flex-1"
                    href={createdLaterMeeting.join_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {createdLaterMeeting.join_url}
                  </a>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(createdLaterMeeting.join_url);
                      alert('Meeting link copied!');
                    }}
                    className="px-3 py-1.5 rounded-lg bg-[#1A73E8] hover:bg-[#1557B0] text-white text-xs font-bold cursor-pointer flex items-center gap-1"
                  >
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy</span>
                  </button>
                </div>

                <p className={
                  createdLaterMeeting.invitation_dispatch?.status === 'success' ? 'text-xs text-emerald-700'
                    : createdLaterMeeting.invitation_dispatch?.status === 'failed' ? 'text-xs text-rose-700'
                      : 'text-xs text-amber-800'
                }>
                  Invitation dispatch: {createdLaterMeeting.invitation_dispatch?.status || 'unknown'}
                  {createdLaterMeeting.invitation_dispatch?.error_message ? ` — ${createdLaterMeeting.invitation_dispatch.error_message}` : ''}
                </p>

                <div className="flex justify-end pt-2">
                  <button
                    onClick={() => setShowLaterLinkModal(false)}
                    className="px-4 py-2 rounded-xl bg-[#F1F5F9] text-[#0F172A] text-xs font-semibold cursor-pointer"
                  >
                    Done
                  </button>
                </div>
              </div>
            </div>
          )}

        </div>
      ) : (
        /* ==================== GOOGLE MEET-STYLE LIVE CONFERENCE ==================== */
        <div className="rounded-3xl bg-[#131417] text-white border border-white/10 shadow-2xl overflow-hidden flex flex-col min-h-[calc(100vh-7.5rem)]">

          {/* Top Conference Header */}
          <header className="px-4 sm:px-6 py-3 bg-[#1B1C20] border-b border-white/10 flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-[#1A73E8] to-[#2563EB] flex items-center justify-center shadow-md shrink-0">
                <Sparkles className="w-4 h-4 text-white" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-extrabold tracking-wide text-[#8AB4F8] uppercase">MeetMind AI</span>
                  <span className="text-white/30">•</span>
                  <h2 className="text-sm font-bold text-white truncate max-w-[200px] sm:max-w-xs">{meetingTitle}</h2>
                </div>
                <div className="flex items-center gap-2 text-[11px] text-white/60 mt-0.5">
                  <button
                    type="button"
                    onClick={copyMeetingLink}
                    className="flex items-center gap-1 hover:text-white transition cursor-pointer font-mono"
                    title="Copy meeting code & invite link"
                  >
                    <span>Code: {roomId || currentMeetingId || 'room'}</span>
                    {copiedLink ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                  </button>
                  <span className="text-white/25">|</span>
                  <span className="text-white/70">Host: <strong className="text-white">{currentMeeting?.host_name || 'Team Leader'}</strong></span>
                  <span className="text-white/25">|</span>
                  <span className="flex items-center gap-1 text-emerald-400 font-medium">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                    <span>{wsSignalingRef.current?.readyState === WebSocket.OPEN ? 'Connected' : 'Ready'}</span>
                  </span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2.5 flex-wrap">
              {/* Recording / AI Listening Indicator */}
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#28292D] border border-white/10 text-xs">
                <span className={`w-2 h-2 rounded-full ${
                  !isMeetingActive ? 'bg-slate-400' : isRecordingPaused ? 'bg-amber-400' : 'bg-rose-500 animate-pulse'
                }`} />
                <span className="font-mono font-semibold text-white">{formatTimer(recordingTime)}</span>
                <span className="text-[11px] text-white/75 hidden sm:inline">
                  {!isMeetingActive ? 'Standby' : isRecordingPaused ? 'Paused' : 'AI Listening'}
                </span>
                {isMeetingActive && (
                  <canvas
                    ref={waveformCanvasRef}
                    width={64}
                    height={16}
                    className="rounded bg-black/40 hidden sm:block"
                    title={`Mic Level: ${audioLevel}%`}
                  />
                )}
              </div>

              <button
                type="button"
                onClick={handleLeaveConference}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-xs font-semibold text-white/80 hover:text-white transition cursor-pointer"
              >
                <ArrowRight className="w-3.5 h-3.5 rotate-180" />
                <span className="hidden sm:inline">Hub</span>
              </button>
            </div>
          </header>

          {/* System / VAD / Mic / Error Banners */}
          {(failedAudioBlob || vadNotice || micStatusWarning || errorMessage) && (
            <div className="px-4 sm:px-6 pt-3 space-y-2 bg-[#131417]">
              {failedAudioBlob && (
                <div className="p-3 rounded-xl bg-amber-500/15 border border-amber-500/30 text-amber-200 text-xs flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
                    <span>Meeting audio is preserved in memory ({failedAudioDuration}). Ready to re-process.</span>
                  </div>
                  <button
                    onClick={handleRetryUpload}
                    disabled={isProcessing}
                    className="px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-black text-xs font-bold cursor-pointer shrink-0"
                  >
                    {isProcessing ? 'Processing...' : 'Retry Upload & Analysis'}
                  </button>
                </div>
              )}

              {vadNotice && (
                <div className="p-3 rounded-xl bg-amber-500/15 border border-amber-500/30 text-amber-200 text-xs flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
                    <span>{vadNotice}</span>
                  </div>
                  <button onClick={() => setVadNotice('')} className="text-amber-300 hover:text-white cursor-pointer"><X className="w-3.5 h-3.5" /></button>
                </div>
              )}

              {micStatusWarning && (
                <div className="p-3 rounded-xl bg-amber-500/15 border border-amber-500/30 text-amber-200 text-xs flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
                    <span>{micStatusWarning}</span>
                  </div>
                  <button onClick={() => setMicStatusWarning('')} className="text-amber-300 hover:text-white cursor-pointer"><X className="w-3.5 h-3.5" /></button>
                </div>
              )}

              {errorMessage && (
                <div className="p-3 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-200 text-xs flex items-center justify-between gap-3 flex-wrap">
                  <div className="flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
                    <span>{errorMessage}</span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {currentMeetingId && (
                      <>
                        <button
                          onClick={handleRetryTranscription}
                          disabled={isProcessing}
                          className="px-2.5 py-1 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-[11px] font-semibold cursor-pointer"
                        >
                          Retry Transcription
                        </button>
                        <button
                          onClick={handleRetryAnalysis}
                          disabled={isProcessing}
                          className="px-2.5 py-1 rounded-lg bg-white/15 hover:bg-white/25 text-white text-[11px] font-semibold cursor-pointer"
                        >
                          Retry AI Analysis
                        </button>
                      </>
                    )}
                    <button onClick={() => setErrorMessage('')} className="text-rose-300 hover:text-white cursor-pointer"><X className="w-3.5 h-3.5" /></button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Pre-Meeting Title/Room Bar (only before meeting starts) */}
          {!isMeetingActive && (
            <div className="px-4 sm:px-6 pt-3 bg-[#131417]">
              <div className="p-3 rounded-2xl bg-[#1B1C20] border border-white/10 grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-semibold text-white/60 mb-1">Meeting Title</label>
                  <input
                    type="text"
                    value={meetingTitle}
                    onChange={(e) => setMeetingTitle(e.target.value)}
                    placeholder="e.g. Architecture Sync"
                    className="w-full px-3 py-1.5 rounded-xl bg-[#131417] border border-white/10 text-xs font-semibold text-white focus:outline-none focus:border-[#8AB4F8]"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-white/60 mb-1">Room Code (Share with participants)</label>
                  <input
                    type="text"
                    value={roomId}
                    onChange={(e) => setRoomId(e.target.value)}
                    placeholder="e.g. sprint-sync-room"
                    className="w-full px-3 py-1.5 rounded-xl bg-[#131417] border border-white/10 text-xs font-mono text-white focus:outline-none focus:border-[#8AB4F8]"
                  />
                </div>
              </div>
            </div>
          )}

          {/* Main Stage + Collapsible Right Side Panel */}
          <div className="flex-1 flex flex-col lg:flex-row overflow-hidden relative">

            {/* Center: Video Grid / Screen Share Presentation */}
            <div className="flex-1 flex flex-col justify-between p-4 sm:p-5 overflow-y-auto relative">

              {isScreenSharing ? (
                /* Screen Sharing Presentation Layout */
                <div className="flex-1 flex flex-col lg:flex-row gap-4 h-full min-h-[380px]">
                  <div className="flex-1 relative rounded-2xl bg-[#202124] border border-[#8AB4F8]/40 overflow-hidden flex flex-col shadow-2xl">
                    <div className="px-4 py-2 bg-[#1A73E8]/90 text-white text-xs font-semibold flex items-center justify-between z-10">
                      <div className="flex items-center gap-2">
                        <Monitor className="w-4 h-4" />
                        <span>You are presenting your screen</span>
                      </div>
                      <button
                        type="button"
                        onClick={handleToggleScreenShare}
                        className="px-3 py-1 rounded-lg bg-white text-[#1A73E8] hover:bg-white/90 text-[11px] font-bold cursor-pointer transition"
                      >
                        Stop Presenting
                      </button>
                    </div>
                    <div className="flex-1 relative bg-black flex items-center justify-center">
                      <video
                        ref={screenPreviewRef}
                        autoPlay
                        playsInline
                        muted
                        className="w-full h-full object-contain max-h-[460px]"
                      />
                    </div>
                  </div>

                  {/* Compact Participant Strip alongside Presentation */}
                  <div className="w-full lg:w-64 flex lg:flex-col gap-3 overflow-x-auto lg:overflow-y-auto shrink-0">
                    {/* Local Host Tile */}
                    <div className={`relative rounded-2xl overflow-hidden bg-[#202124] border min-w-[180px] h-36 lg:h-40 flex items-center justify-center shrink-0 ${
                      activeSpeakerId === 'user_local' ? 'border-emerald-400 ring-2 ring-emerald-400/30' : 'border-white/10'
                    }`}>
                      <video
                        ref={localVideoRef}
                        autoPlay
                        playsInline
                        muted
                        className={`w-full h-full object-cover transform scale-x-[-1] absolute inset-0 ${isCamEnabled ? 'block' : 'hidden'}`}
                      />
                      {!isCamEnabled && (
                        <div className="w-12 h-12 rounded-full bg-[#1A73E8] text-white flex items-center justify-center font-bold text-sm z-1">
                          {getInitials(user?.name || 'You')}
                        </div>
                      )}
                      <div className="absolute bottom-2 left-2 z-10 flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-black/70 text-[11px]">
                        {isMicMuted ? <MicOff className="w-3 h-3 text-rose-400" /> : <Mic className="w-3 h-3 text-emerald-400" />}
                        <span className="font-medium truncate max-w-[110px]">{user?.name || 'You'}</span>
                      </div>
                    </div>

                    {remotePeers.map((peer) => (
                      <div key={peer.peer_id} className="relative rounded-2xl overflow-hidden bg-[#202124] border border-white/10 min-w-[180px] h-36 lg:h-40 flex items-center justify-center shrink-0">
                        <video
                          autoPlay
                          playsInline
                          ref={(el) => {
                            if (el && peer.stream && el.srcObject !== peer.stream) el.srcObject = peer.stream;
                          }}
                          className={`w-full h-full object-cover absolute inset-0 ${peer.video_enabled ? 'block' : 'hidden'}`}
                        />
                        {!peer.video_enabled && (
                          <div className="w-12 h-12 rounded-full bg-[#34A853] text-white flex items-center justify-center font-bold text-sm z-1">
                            {getInitials(peer.name)}
                          </div>
                        )}
                        <div className="absolute bottom-2 left-2 z-10 flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-black/70 text-[11px]">
                          {peer.audio_enabled ? <Mic className="w-3 h-3 text-emerald-400" /> : <MicOff className="w-3 h-3 text-rose-400" />}
                          <span className="font-medium truncate max-w-[110px]">{peer.name}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : remotePeers.length === 0 ? (
                /* Solo Host View (Google Meet Style) */
                <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-4 max-w-5xl w-full mx-auto items-stretch my-auto">
                  {/* Host Tile */}
                  <div className={`relative rounded-2xl overflow-hidden bg-[#202124] border flex flex-col items-center justify-center min-h-[280px] sm:min-h-[340px] shadow-xl ${
                    activeSpeakerId === 'user_local' ? 'border-emerald-400 ring-2 ring-emerald-400/30' : 'border-white/10'
                  }`}>
                    <video
                      ref={localVideoRef}
                      autoPlay
                      playsInline
                      muted
                      className={`w-full h-full object-cover transform scale-x-[-1] absolute inset-0 ${isCamEnabled ? 'block' : 'hidden'}`}
                    />
                    {!isCamEnabled && (
                      <div className="flex flex-col items-center justify-center space-y-3 z-1">
                        <div className="w-24 h-24 rounded-full bg-gradient-to-tr from-[#1A73E8] to-[#60A5FA] text-white flex items-center justify-center text-3xl font-bold shadow-2xl border-2 border-white/15">
                          {getInitials(user?.name || 'You')}
                        </div>
                        <div className="text-center">
                          <span className="text-sm font-bold text-white block">{user?.name || 'You'}</span>
                          <span className="text-xs text-white/50">{user?.email || 'Host'}</span>
                        </div>
                      </div>
                    )}

                    <div className="absolute top-3 left-3 z-10 flex items-center gap-2">
                      <span className="px-2.5 py-1 rounded-lg bg-[#1A73E8] text-white font-bold text-[10px] tracking-wider uppercase shadow flex items-center gap-1">
                        <Shield className="w-3 h-3" />
                        <span>{isMeetingHost ? 'HOST' : 'PARTICIPANT'}</span>
                      </span>
                    </div>

                    <div className="absolute top-3 right-3 z-10 flex items-center gap-1.5">
                      <span className={`p-1.5 rounded-full ${isCamEnabled ? 'bg-black/50 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
                        {isCamEnabled ? <Video className="w-3.5 h-3.5" /> : <VideoOff className="w-3.5 h-3.5" />}
                      </span>
                    </div>

                    <div className="absolute bottom-3 left-3 z-10 flex items-center gap-2 px-3 py-1.5 rounded-xl bg-black/70 backdrop-blur-md text-white text-xs border border-white/10">
                      {isMicMuted ? <MicOff className="w-3.5 h-3.5 text-rose-400" /> : <Mic className="w-3.5 h-3.5 text-emerald-400" />}
                      <span className="font-semibold">{user?.name ? `${user.name} (You)` : 'You'}</span>
                    </div>
                  </div>

                  {/* Share / Solo Readiness Card */}
                  <div className="rounded-2xl bg-[#202124] border border-white/10 p-6 flex flex-col justify-between items-center text-center shadow-xl min-h-[280px] sm:min-h-[340px]">
                    <div className="space-y-2 mt-2">
                      <div className="w-12 h-12 rounded-2xl bg-[#1A73E8]/15 border border-[#1A73E8]/30 text-[#8AB4F8] flex items-center justify-center mx-auto">
                        <UserPlus className="w-6 h-6" />
                      </div>
                      <h4 className="text-base font-bold text-white">{isMeetingHost ? 'Your meeting is ready' : 'You joined as a participant'}</h4>
                      <p className="text-xs text-white/60 max-w-xs mx-auto leading-relaxed">
                        Meeting host: <strong className="text-white/90">{currentMeeting?.host_name || 'Team Leader'}</strong>
                      </p>
                    </div>

                    <div className="w-full space-y-3 my-4">
                      <div className="flex items-center gap-2 p-2.5 rounded-xl bg-[#131417] border border-white/10">
                        <span className="text-xs font-mono text-white/80 truncate flex-1 text-left px-1">
                          {roomId || currentMeetingId || 'room'}
                        </span>
                        <button
                          type="button"
                          onClick={copyMeetingLink}
                          className="px-3 py-1.5 rounded-lg bg-[#1A73E8] hover:bg-[#1557B0] text-white text-xs font-semibold transition flex items-center gap-1.5 cursor-pointer"
                        >
                          {copiedLink ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                          <span>{copiedLink ? 'Copied' : 'Copy Link'}</span>
                        </button>
                      </div>

                      <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-[11px] text-left leading-relaxed">
                        <strong>MeetMind AI Active:</strong> Speech-to-text, speaker attribution, summary, and task extraction work seamlessly in solo or multi-user sessions.
                      </div>
                    </div>

                    <div className="text-[11px] text-white/40 flex items-center gap-1.5">
                      <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                      <span>WebRTC Mesh & Local Audio Capture Ready</span>
                    </div>
                  </div>
                </div>
              ) : (
                /* Dynamic Multi-Participant Video Grid */
                <div className={`flex-1 grid gap-3 w-full h-full my-auto ${
                  remotePeers.length === 1
                    ? 'grid-cols-1 md:grid-cols-2'
                    : remotePeers.length <= 3
                    ? 'grid-cols-1 sm:grid-cols-2'
                    : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3'
                }`}>
                  {/* Local Host Tile */}
                  <div className={`relative rounded-2xl overflow-hidden bg-[#202124] border flex flex-col items-center justify-center min-h-[240px] shadow-lg ${
                    activeSpeakerId === 'user_local' ? 'border-emerald-400 ring-2 ring-emerald-400/40' : 'border-white/10'
                  }`}>
                    <video
                      ref={localVideoRef}
                      autoPlay
                      playsInline
                      muted
                      className={`w-full h-full object-cover transform scale-x-[-1] absolute inset-0 ${isCamEnabled ? 'block' : 'hidden'}`}
                    />
                    {!isCamEnabled && (
                      <div className="flex flex-col items-center justify-center space-y-2 z-1">
                        <div className="w-20 h-20 rounded-full bg-[#1A73E8] text-white flex items-center justify-center text-2xl font-bold shadow-lg">
                          {getInitials(user?.name || 'You')}
                        </div>
                        <span className="text-xs font-semibold text-white/90">{user?.name || 'You'}</span>
                      </div>
                    )}
                    <div className="absolute top-3 left-3 z-10">
                      <span className="px-2 py-0.5 rounded-md bg-[#1A73E8] text-white font-bold text-[10px] uppercase flex items-center gap-1">
                        <Shield className="w-3 h-3" />
                        <span>{isMeetingHost ? 'HOST' : 'PARTICIPANT'}</span>
                      </span>
                    </div>
                    <div className="absolute top-3 right-3 z-10">
                      <span className={`p-1.5 rounded-full inline-flex ${isCamEnabled ? 'bg-black/50 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
                        {isCamEnabled ? <Video className="w-3.5 h-3.5" /> : <VideoOff className="w-3.5 h-3.5" />}
                      </span>
                    </div>
                    <div className="absolute bottom-3 left-3 z-10 flex items-center gap-2 px-2.5 py-1 rounded-lg bg-black/70 backdrop-blur-md text-white text-xs">
                      {isMicMuted ? <MicOff className="w-3.5 h-3.5 text-rose-400" /> : <Mic className="w-3.5 h-3.5 text-emerald-400" />}
                      <span className="font-medium">{user?.name ? `${user.name} (You)` : 'You'}</span>
                    </div>
                  </div>

                  {/* Remote WebRTC Peer Tiles */}
                  {remotePeers.map((peer) => (
                    <div key={peer.peer_id} className="relative rounded-2xl overflow-hidden bg-[#202124] border border-white/10 flex flex-col items-center justify-center min-h-[240px] shadow-lg">
                      <video
                        autoPlay
                        playsInline
                        ref={(el) => {
                          if (el && peer.stream && el.srcObject !== peer.stream) {
                            el.srcObject = peer.stream;
                          }
                        }}
                        className={`w-full h-full object-cover absolute inset-0 ${peer.video_enabled ? 'block' : 'hidden'}`}
                      />
                      {!peer.video_enabled && (
                        <div className="flex flex-col items-center justify-center space-y-2 z-1">
                          <div className="w-20 h-20 rounded-full bg-[#34A853] text-white flex items-center justify-center text-2xl font-bold shadow-lg">
                            {getInitials(peer.name)}
                          </div>
                          <span className="text-xs font-semibold text-white/90">{peer.name}</span>
                        </div>
                      )}
                      <div className="absolute top-3 right-3 z-10">
                        <span className={`p-1.5 rounded-full inline-flex ${peer.video_enabled ? 'bg-black/50 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
                          {peer.video_enabled ? <Video className="w-3.5 h-3.5" /> : <VideoOff className="w-3.5 h-3.5" />}
                        </span>
                      </div>
                      <div className="absolute bottom-3 left-3 z-10 flex items-center gap-2 px-2.5 py-1 rounded-lg bg-black/70 backdrop-blur-md text-white text-xs">
                        {peer.audio_enabled ? <Mic className="w-3.5 h-3.5 text-emerald-400" /> : <MicOff className="w-3.5 h-3.5 text-rose-400" />}
                        <span className="font-medium">{peer.name} ({peer.role || 'Member'})</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Live Closed Captions Overlay */}
              {showClosedCaptions && latestSubtitle.text && (
                <div className="pt-3 flex items-center justify-center z-10">
                  <div className="max-w-2xl px-4 py-2 rounded-xl bg-black/80 backdrop-blur-md border border-white/10 text-white text-xs shadow-xl text-center">
                    <span className="font-bold text-[#8AB4F8] mr-1.5">{latestSubtitle.speaker}:</span>
                    <span>{latestSubtitle.text}</span>
                  </div>
                </div>
              )}
            </div>

            {/* Collapsible Right-Side Panel (AI Assistant / Participants / Chat / Diagnostics) */}
            {isSidePanelOpen && (
              <aside className="w-full lg:w-[400px] xl:w-[430px] bg-[#1B1C20] border-t lg:border-t-0 lg:border-l border-white/10 flex flex-col max-h-[540px] lg:max-h-[calc(100vh-12rem)] shrink-0">

                {/* Panel Header */}
                <div className="px-4 py-3 border-b border-white/10 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {sidePanelTab === 'people' ? (
                      <>
                        <Users className="w-4 h-4 text-[#8AB4F8]" />
                        <h3 className="text-xs font-bold text-white">Participants ({remotePeers.length + 1})</h3>
                      </>
                    ) : sidePanelTab === 'chat' ? (
                      <>
                        <MessageSquare className="w-4 h-4 text-[#8AB4F8]" />
                        <h3 className="text-xs font-bold text-white">In-Call Messages</h3>
                      </>
                    ) : sidePanelTab === 'diagnostics' ? (
                      <>
                        <Cpu className="w-4 h-4 text-[#8AB4F8]" />
                        <h3 className="text-xs font-bold text-white">Pipeline Diagnostics</h3>
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-4 h-4 text-[#8AB4F8]" />
                        <h3 className="text-xs font-bold text-white">MeetMind AI Assistant</h3>
                      </>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => setIsSidePanelOpen(false)}
                    className="p-1.5 rounded-lg hover:bg-white/10 text-white/60 hover:text-white transition cursor-pointer"
                    title="Close panel"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                {/* 4-Tab Bar when in AI Assistant Mode */}
                {['transcript', 'insights', 'tasks', 'summary', 'intel'].includes(sidePanelTab) && (
                  <div className="px-3 py-2 border-b border-white/10 bg-[#131417]/60 grid grid-cols-4 gap-1">
                    {[
                      { id: 'transcript', label: 'Transcript' },
                      { id: 'insights', label: 'AI Insights' },
                      { id: 'tasks', label: `Tasks (${extractedTasks.length})` },
                      { id: 'summary', label: 'Summary' },
                    ].map((tab) => (
                      <button
                        key={tab.id}
                        type="button"
                        onClick={() => setSidePanelTab(tab.id)}
                        className={`px-2 py-1.5 rounded-lg text-[11px] font-semibold transition cursor-pointer truncate ${
                          (sidePanelTab === tab.id || (tab.id === 'summary' && sidePanelTab === 'intel'))
                            ? 'bg-[#1A73E8] text-white shadow'
                            : 'text-white/60 hover:text-white hover:bg-white/5'
                        }`}
                      >
                        {tab.label}
                      </button>
                    ))}
                  </div>
                )}

                {/* Multi-Agent Progress Bar */}
                {isProcessing && (
                  <div className="p-3 bg-[#1A73E8]/15 border-b border-[#1A73E8]/30 space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold text-[#8AB4F8] flex items-center gap-1.5">
                        <Cpu className="w-3.5 h-3.5 animate-spin" />
                        <span>Stage {processingStep}: {agentSteps[processingStep - 1]?.name || 'Processing'}</span>
                      </span>
                      <span className="text-[#8AB4F8] font-bold">{processingStep}/8</span>
                    </div>
                    <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
                      <div className="h-full bg-[#1A73E8] transition-all" style={{ width: `${(processingStep / 8) * 100}%` }} />
                    </div>
                    <p className="text-[10px] text-white/70">{agentSteps[processingStep - 1]?.desc}</p>
                  </div>
                )}

                {/* Panel Scrollable Body */}
                <div className="flex-1 overflow-y-auto p-3.5 space-y-3">

                  {/* AI TAB 1: Live Transcript */}
                  {sidePanelTab === 'transcript' && (
                    <div className="space-y-2.5 text-xs">
                      {transcripts.length > 0 ? (
                        transcripts.map((seg, idx) => (
                          <div key={idx} className="p-3 rounded-xl bg-[#202124] border border-white/10 space-y-1">
                            <div className="flex items-center justify-between">
                              <span className="font-bold text-[#8AB4F8]">{seg.speaker_label || `Speaker ${seg.speaker_id || 1}`}</span>
                              <span className="text-[10px] text-white/50 font-mono">
                                {seg.start?.toFixed ? `${seg.start.toFixed(1)}s` : '00:00'}
                              </span>
                            </div>
                            <p className="text-white/90 leading-relaxed">{seg.text}</p>
                          </div>
                        ))
                      ) : (
                        <div className="p-8 text-center text-xs text-white/50 space-y-2">
                          <Mic className="w-6 h-6 text-white/40 mx-auto" />
                          <p>Start the meeting to capture audio and generate your transcript.</p>
                          <p className="text-[11px] text-white/40">Tamil, Tanglish, and English speech supported.</p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* AI TAB 2: AI Insights (LangGraph Analysis) */}
                  {sidePanelTab === 'insights' && (
                    <div className="space-y-3 text-xs">
                      {!currentMeeting ? (
                        <div className="p-8 text-center text-white/50 space-y-1">
                          <Sparkles className="w-6 h-6 text-white/40 mx-auto mb-2" />
                          <p>AI Insights will appear after the meeting is analyzed.</p>
                        </div>
                      ) : (
                        <>
                          <div className="p-3 rounded-xl bg-[#202124] border border-white/10 space-y-1.5">
                            <span className="font-bold text-[#8AB4F8] block">Discussion Points</span>
                            {currentMeeting.discussion_topics?.length > 0 ? (
                              <ul className="list-disc pl-4 space-y-1 text-white/85">
                                {currentMeeting.discussion_topics.map((topic, i) => <li key={i}>{topic}</li>)}
                              </ul>
                            ) : (
                              <p className="text-white/50 italic">No discussion topics recorded.</p>
                            )}
                          </div>

                          <div className="p-3 rounded-xl bg-[#202124] border border-white/10 space-y-1.5">
                            <span className="font-bold text-emerald-400 block">Decisions</span>
                            {(currentMeeting.key_decisions || currentMeeting.decisions)?.length > 0 ? (
                              <ul className="list-disc pl-4 space-y-1 text-white/85">
                                {(currentMeeting.key_decisions || currentMeeting.decisions).map((dec, i) => <li key={i}>{dec}</li>)}
                              </ul>
                            ) : (
                              <p className="text-white/50 italic">No explicit decisions detected.</p>
                            )}
                          </div>

                          <div className="p-3 rounded-xl bg-[#202124] border border-white/10 space-y-1.5">
                            <span className="font-bold text-purple-300 block">Important Observations</span>
                            {currentMeeting.important_outcomes?.length > 0 ? (
                              <ul className="list-disc pl-4 space-y-1 text-white/85">
                                {currentMeeting.important_outcomes.map((obs, i) => <li key={i}>{obs}</li>)}
                              </ul>
                            ) : (
                              <p className="text-white/50 italic">No additional observations recorded.</p>
                            )}
                          </div>

                          <div className="p-3 rounded-xl bg-[#202124] border border-white/10 space-y-1.5">
                            <span className="font-bold text-amber-300 block">Pending Questions</span>
                            {currentMeeting.unresolved_questions?.length > 0 ? (
                              <ul className="list-disc pl-4 space-y-1 text-white/85">
                                {currentMeeting.unresolved_questions.map((q, i) => <li key={i}>{q}</li>)}
                              </ul>
                            ) : (
                              <p className="text-white/50 italic">No pending questions.</p>
                            )}
                          </div>
                        </>
                      )}
                    </div>
                  )}

                  {/* AI TAB 3: Detected Tasks */}
                  {sidePanelTab === 'tasks' && (
                    <div className="space-y-3 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-white">Detected Action Items</span>
                        <span className="text-[11px] text-white/50">Human Approval Required</span>
                      </div>

                      {extractedTasks.length > 0 ? (
                        extractedTasks.map((task) => {
                          const isApproved = approvedTaskIds.has(task.task_id) || task.approval_status === 'Approved';
                          const isRejected = rejectedTaskIds.has(task.task_id) || task.approval_status === 'Rejected';
                          const isEditing = editingTask?.task_id === task.task_id;

                          if (isEditing) {
                            return (
                              <div key={task.task_id} className="p-3.5 rounded-xl bg-[#202124] border border-[#8AB4F8]/40 space-y-2.5">
                                <span className="font-mono text-[10px] text-[#8AB4F8] font-bold block">Edit Task {task.task_id}</span>
                                <div>
                                  <label className="block text-[11px] text-white/60 mb-1">Title</label>
                                  <input
                                    type="text"
                                    value={editingTask.title}
                                    onChange={(e) => setEditingTask({ ...editingTask, title: e.target.value })}
                                    className="w-full px-2.5 py-1.5 rounded-lg bg-[#131417] border border-white/15 text-xs text-white"
                                  />
                                </div>
                                <div className="grid grid-cols-2 gap-2">
                                  <div>
                                    <label className="block text-[11px] text-white/60 mb-1">Assignee</label>
                                    <select
                                      value={editingTask.assigned_member_name}
                                      onChange={(e) => {
                                        const selectedMember = activeMembers.find(m => m.name === e.target.value);
                                        const selectedLeader = e.target.value === currentMeeting?.host_name;
                                        setEditingTask({
                                          ...editingTask,
                                          assigned_member_name: e.target.value,
                                          assigned_member_id: selectedMember?.member_id || (selectedLeader ? currentMeeting?.host_id : null),
                                          assigned_member_email: selectedMember?.email || (selectedLeader ? currentMeeting?.host_email : null),
                                          assigned_member_role: selectedMember?.role || (selectedLeader ? 'Team Leader' : 'Member')
                                        });
                                      }}
                                      className="w-full px-2 py-1.5 rounded-lg bg-[#131417] border border-white/15 text-xs text-white"
                                    >
                                      <option value={currentMeeting?.host_name || 'Team Leader'}>{currentMeeting?.host_name || 'Team Leader'} (Team Leader)</option>
                                      {activeMembers.map((m) => (
                                        <option key={m.member_id} value={m.name}>{m.name} ({m.role})</option>
                                      ))}
                                      <option value="Unassigned">Unassigned</option>
                                    </select>
                                  </div>
                                  <div>
                                    <label className="block text-[11px] text-white/60 mb-1">Priority</label>
                                    <select
                                      value={editingTask.priority || 'Medium'}
                                      onChange={(e) => setEditingTask({ ...editingTask, priority: e.target.value })}
                                      className="w-full px-2 py-1.5 rounded-lg bg-[#131417] border border-white/15 text-xs text-white"
                                    >
                                      <option value="Critical">Critical</option>
                                      <option value="High">High</option>
                                      <option value="Medium">Medium</option>
                                      <option value="Low">Low</option>
                                    </select>
                                  </div>
                                </div>
                                <div>
                                  <label className="block text-[11px] text-white/60 mb-1">Deadline</label>
                                  <input
                                    type="text"
                                    value={editingTask.deadline || ''}
                                    onChange={(e) => setEditingTask({ ...editingTask, deadline: e.target.value })}
                                    placeholder="e.g. Friday"
                                    className="w-full px-2.5 py-1 rounded-lg bg-[#131417] border border-white/15 text-xs text-white"
                                  />
                                </div>
                                <div className="flex items-center gap-2 pt-1">
                                  <button onClick={handleCancelEditTask} className="px-3 py-1 rounded-lg border border-white/15 text-white/70 hover:text-white text-xs cursor-pointer">Cancel</button>
                                  <button onClick={handleSaveTaskEdit} className="flex-1 py-1 rounded-lg bg-[#1A73E8] hover:bg-[#1557B0] text-white text-xs font-semibold cursor-pointer">Save</button>
                                </div>
                              </div>
                            );
                          }

                          return (
                            <div key={task.task_id} className="p-3.5 rounded-xl bg-[#202124] border border-white/10 space-y-2.5">
                              <div className="flex items-start justify-between gap-2">
                                <div className="space-y-1">
                                  <div className="flex items-center gap-1.5 flex-wrap">
                                    <span className="font-mono text-[10px] text-[#8AB4F8] font-bold bg-[#1A73E8]/20 px-1.5 py-0.5 rounded">{task.task_id}</span>
                                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                                      task.priority === 'Critical' ? 'bg-rose-500/20 text-rose-300' :
                                      task.priority === 'High' ? 'bg-orange-500/20 text-orange-300' :
                                      task.priority === 'Low' ? 'bg-white/10 text-white/60' :
                                      'bg-blue-500/20 text-blue-300'
                                    }`}>{task.priority || 'Medium'}</span>
                                  </div>
                                  <h5 className="font-bold text-xs text-white leading-snug">{task.title}</h5>
                                  {task.description && <p className="text-[11px] text-white/70 leading-relaxed">{task.description}</p>}
                                </div>
                                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md shrink-0 ${
                                  isApproved ? 'bg-emerald-500/20 text-emerald-300' :
                                  isRejected ? 'bg-rose-500/20 text-rose-300' :
                                  'bg-amber-500/20 text-amber-300'
                                }`}>
                                  {isApproved ? 'Approved' : isRejected ? 'Rejected' : task.approval_status || 'Needs Approval'}
                                </span>
                              </div>

                              <div className="p-2.5 rounded-lg bg-[#131417] border border-white/10 space-y-1 text-[11px]">
                                <div className="flex items-center justify-between">
                                  <span className="text-white/50">Assigned To:</span>
                                  <span className="font-semibold text-white">{task.assigned_member_name || 'Unassigned'}</span>
                                </div>
                                {task.deadline && (
                                  <div className="flex items-center justify-between">
                                    <span className="text-white/50">Deadline:</span>
                                    <span className="font-semibold text-purple-300">{task.deadline}</span>
                                  </div>
                                )}
                                {task.assignment_reason && (
                                  <p className="text-[10px] text-white/60 pt-1 border-t border-white/10">{task.assignment_reason}</p>
                                )}
                              </div>

                              {!isApproved && !isRejected && isLeader ? (
                                <div className="flex items-center gap-1.5 pt-1">
                                  <button onClick={() => handleStartEditTask(task)} className="px-2.5 py-1.5 rounded-lg border border-white/15 hover:bg-white/5 text-white/80 text-[11px] font-semibold cursor-pointer flex items-center gap-1">
                                    <Edit3 className="w-3 h-3" /><span>Edit</span>
                                  </button>
                                  <button onClick={() => handleRejectTask(task.task_id)} className="px-2.5 py-1.5 rounded-lg border border-white/15 text-rose-300 hover:bg-rose-500/15 text-[11px] font-semibold cursor-pointer">
                                    Reject
                                  </button>
                                  <button onClick={() => handleApproveTask(task.task_id, task)} className="flex-1 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-semibold cursor-pointer flex items-center justify-center gap-1">
                                    <Check className="w-3 h-3" /><span>Approve</span>
                                  </button>
                                </div>
                              ) : (
                                <div className={`text-[11px] font-medium flex items-center gap-1 justify-center py-0.5 ${
                                  isApproved ? 'text-emerald-400' : isRejected ? 'text-rose-400' : 'text-amber-300'
                                }`}>
                                  <CheckCircle2 className="w-3.5 h-3.5" />
                                  <span>{isApproved ? 'Approved & Saved' : isRejected ? 'Rejected' : 'Awaiting Team Leader approval'}</span>
                                </div>
                              )}
                            </div>
                          );
                        })
                      ) : (
                        <div className="p-8 text-center text-xs text-white/50">
                          <p>No action items detected yet.</p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* AI TAB 4: Meeting Summary */}
                  {(sidePanelTab === 'summary' || sidePanelTab === 'intel') && (
                    <div className="space-y-3 text-xs">
                      <div className="p-3.5 rounded-xl bg-[#202124] border border-white/10 space-y-1.5">
                        <span className="font-bold text-[#8AB4F8] block">Executive Summary</span>
                        <p className="text-white/85 leading-relaxed">
                          {currentMeeting?.meeting_summary || currentMeeting?.summary || 'Meeting summary will be generated once the session completes.'}
                        </p>
                      </div>

                      {(currentMeeting?.key_decisions || currentMeeting?.decisions)?.length > 0 && (
                        <div className="p-3.5 rounded-xl bg-[#202124] border border-white/10 space-y-1.5">
                          <span className="font-bold text-emerald-400 block">Key Decisions</span>
                          <ul className="list-disc pl-4 space-y-1 text-white/85">
                            {(currentMeeting.key_decisions || currentMeeting.decisions).map((dec, i) => (
                              <li key={i}>{dec}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {extractedTasks.length > 0 && (
                        <div className="p-3.5 rounded-xl bg-[#202124] border border-white/10 space-y-2">
                          <span className="font-bold text-amber-300 block">Action Items & Responsibilities</span>
                          <div className="space-y-1.5">
                            {extractedTasks.map((t) => (
                              <div key={t.task_id} className="flex items-center justify-between gap-2 p-2 rounded-lg bg-[#131417] border border-white/10">
                                <span className="text-white/90 truncate">{t.title}</span>
                                <span className="text-[10px] font-bold text-[#8AB4F8] shrink-0">{t.assigned_member_name || 'Unassigned'}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* PARTICIPANTS PANEL */}
                  {sidePanelTab === 'people' && (
                    <div className="space-y-3 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="text-white/60 font-semibold">Joined ({remotePeers.length + 1})</span>
                        <button onClick={copyMeetingLink} className="text-[#8AB4F8] hover:underline font-semibold flex items-center gap-1 cursor-pointer">
                          <Copy className="w-3 h-3" />
                          <span>{copiedLink ? 'Copied' : 'Invite'}</span>
                        </button>
                      </div>
                      <p className="text-[11px] text-white/60">Host: <strong className="text-white">{currentMeeting?.host_name || 'Team Leader'}</strong></p>

                      {/* Local participant */}
                      <div className="p-3 rounded-xl bg-[#202124] border border-[#8AB4F8]/30 flex items-center justify-between">
                        <div className="flex items-center gap-2.5">
                          <div className="w-9 h-9 rounded-full bg-[#1A73E8] text-white flex items-center justify-center font-bold text-xs">
                            {getInitials(user?.name || 'You')}
                          </div>
                          <div>
                            <div className="flex items-center gap-1.5">
                              <span className="font-bold text-white">{user?.name || 'You'}</span>
                              <span className="px-1.5 py-0.5 rounded bg-[#1A73E8] text-white font-bold text-[9px] uppercase">{isMeetingHost ? 'HOST' : 'PARTICIPANT'}</span>
                            </div>
                            <span className="text-[11px] text-white/50">{user?.email || 'Meeting Organizer'}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {isMicMuted ? <MicOff className="w-4 h-4 text-rose-400" /> : <Mic className="w-4 h-4 text-emerald-400" />}
                          {isCamEnabled ? <Video className="w-4 h-4 text-emerald-400" /> : <VideoOff className="w-4 h-4 text-rose-400" />}
                        </div>
                      </div>

                      {remotePeers.map((peer) => (
                        <div key={peer.peer_id} className="p-3 rounded-xl bg-[#202124] border border-white/10 flex items-center justify-between">
                          <div className="flex items-center gap-2.5">
                            <div className="w-9 h-9 rounded-full bg-[#34A853] text-white flex items-center justify-center font-bold text-xs">
                              {getInitials(peer.name)}
                            </div>
                            <div>
                              <span className="font-bold text-white block">{peer.name}</span>
                              <span className="text-[11px] text-white/50">{peer.role || 'Participant'}</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-1.5">
                            {peer.audio_enabled ? <Mic className="w-4 h-4 text-emerald-400" /> : <MicOff className="w-4 h-4 text-rose-400" />}
                            {peer.video_enabled ? <Video className="w-4 h-4 text-emerald-400" /> : <VideoOff className="w-4 h-4 text-rose-400" />}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* CHAT PANEL */}
                  {sidePanelTab === 'chat' && (
                    <div className="flex flex-col h-full min-h-[300px] space-y-3">
                      <div className="flex-1 overflow-y-auto space-y-2.5 text-xs">
                        {inMeetingMessages.length === 0 ? (
                          <div className="text-center text-white/50 py-10 space-y-1">
                            <MessageSquare className="w-6 h-6 text-white/30 mx-auto" />
                            <p>No messages yet. Messages sent here are visible to everyone in the call.</p>
                          </div>
                        ) : (
                          inMeetingMessages.map((msg, i) => (
                            <div key={i} className="p-2.5 rounded-xl bg-[#202124] border border-white/10 space-y-1">
                              <div className="flex items-center justify-between">
                                <span className="font-bold text-[11px] text-[#8AB4F8]">{msg.sender_name}</span>
                                <span className="text-[10px] text-white/40 font-mono">
                                  {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
                                </span>
                              </div>
                              <p className="text-white/90">{msg.text}</p>
                            </div>
                          ))
                        )}
                      </div>
                      <form onSubmit={handleSendInMeetingChat} className="flex gap-2 pt-2 border-t border-white/10">
                        <input
                          type="text"
                          value={chatInput}
                          onChange={(e) => setChatInput(e.target.value)}
                          placeholder="Send a message to everyone..."
                          className="flex-1 px-3 py-2 rounded-xl bg-[#131417] border border-white/15 text-xs text-white focus:outline-none focus:border-[#8AB4F8]"
                        />
                        <button type="submit" className="p-2 rounded-xl bg-[#1A73E8] hover:bg-[#1557B0] text-white cursor-pointer transition">
                          <Send className="w-4 h-4" />
                        </button>
                      </form>
                    </div>
                  )}

                  {/* DIAGNOSTICS PANEL */}
                  {sidePanelTab === 'diagnostics' && (
                    <div className="space-y-2.5 text-xs">
                      <div className="flex items-center justify-between pb-2 border-b border-white/10">
                        <span className="font-bold text-white">Pipeline Diagnostics</span>
                        <button
                          onClick={() => fetchDiagnostics(currentMeetingId)}
                          disabled={isLoadingDiagnostics}
                          className="px-2 py-1 rounded bg-white/10 hover:bg-white/20 text-white text-[10px] font-semibold flex items-center gap-1 cursor-pointer"
                        >
                          <RotateCcw className={`w-3 h-3 ${isLoadingDiagnostics ? 'animate-spin' : ''}`} />
                          <span>Refresh</span>
                        </button>
                      </div>
                      {isLoadingDiagnostics ? (
                        <div className="p-6 text-center text-white/50">Loading telemetry...</div>
                      ) : diagnosticsData ? (
                        <div className="space-y-2 text-[11px]">
                          <div className="p-2.5 rounded-xl bg-[#202124] border border-white/10 space-y-1 font-mono text-[10px]">
                            <div className="flex justify-between font-sans text-xs font-bold text-white">
                              <span>Audio Validation</span>
                              <span className={diagnosticsData.audio?.decodable ? 'text-emerald-400' : 'text-amber-400'}>
                                {diagnosticsData.audio?.decodable ? 'Decodable ✓' : 'Pending'}
                              </span>
                            </div>
                            <p className="text-white/70">MIME: {diagnosticsData.audio?.mime_type || 'N/A'} | Size: {diagnosticsData.audio?.file_size_bytes ? `${Math.round(diagnosticsData.audio.file_size_bytes / 1024)} KB` : 'N/A'}</p>
                            <p className="text-white/70">Captured: {diagnosticsData.audio?.duration || '00:00'} | Decoded: {diagnosticsData.audio?.decoded_duration_seconds ?? 0}s</p>
                            <p className="text-white/70">{diagnosticsData.audio?.sample_rate || 0} Hz, {diagnosticsData.audio?.channels || 0} ch | Max {diagnosticsData.audio?.max_dbfs ?? -120} dBFS</p>
                          </div>
                          <div className="p-2.5 rounded-xl bg-[#202124] border border-white/10 space-y-1">
                            <div className="flex justify-between font-bold text-white">
                              <span>Transcription</span>
                              <span className="text-[#8AB4F8]">{diagnosticsData.transcription?.segment_count || 0} segments</span>
                            </div>
                            <p className="text-white/70">{diagnosticsData.transcription?.total_words || 0} words</p>
                          </div>
                          <div className="p-2.5 rounded-xl bg-[#202124] border border-white/10 flex justify-between">
                            <span className="font-bold text-white">Automation Guard</span>
                            <span className="text-emerald-400 font-bold">
                              {diagnosticsData.automation_safety?.enable_automation_dispatch ? 'Enabled' : 'Disabled (Safe Mode) ✓'}
                            </span>
                          </div>
                        </div>
                      ) : (
                        <p className="text-white/50 text-center py-6">Complete a meeting or click Refresh to view diagnostics.</p>
                      )}
                    </div>
                  )}

                </div>
              </aside>
            )}
          </div>

          {/* Google Meet-Inspired Bottom Control Bar */}
          <footer className="px-4 sm:px-6 py-3 bg-[#1B1C20] border-t border-white/10 flex items-center justify-between gap-3 flex-wrap relative">

            {/* Left: Mic Device Selector */}
            <div className="flex items-center gap-2">
              {audioInputDevices.length > 0 && (
                <select
                  value={selectedMicId}
                  onChange={(e) => setSelectedMicId(e.target.value)}
                  disabled={isMeetingActive}
                  title={`Microphone (${micPermission})`}
                  className="max-w-[160px] truncate px-2.5 py-1.5 rounded-xl bg-[#28292D] border border-white/10 text-[11px] text-white/90 focus:outline-none disabled:opacity-60"
                >
                  {audioInputDevices.map((dev, idx) => (
                    <option key={dev.deviceId || idx} value={dev.deviceId}>
                      {dev.label || `Microphone ${idx + 1}`}
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* Center: Core Google Meet Controls */}
            <div className="flex items-center gap-2 sm:gap-2.5 mx-auto flex-wrap justify-center">
              <button
                type="button"
                onClick={handleToggleMic}
                title={isMicMuted ? 'Turn on microphone' : 'Turn off microphone'}
                className={`w-11 h-11 rounded-full flex items-center justify-center transition cursor-pointer ${
                  isMicMuted ? 'bg-[#EA4335] hover:bg-[#D93025] text-white' : 'bg-[#3C4043] hover:bg-[#4A4E51] text-white'
                }`}
              >
                {isMicMuted ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
              </button>

              <button
                type="button"
                onClick={handleToggleCam}
                title={isCamEnabled ? 'Turn off camera' : 'Turn on camera'}
                className={`w-11 h-11 rounded-full flex items-center justify-center transition cursor-pointer ${
                  !isCamEnabled ? 'bg-[#EA4335] hover:bg-[#D93025] text-white' : 'bg-[#3C4043] hover:bg-[#4A4E51] text-white'
                }`}
              >
                {isCamEnabled ? <Video className="w-4 h-4" /> : <VideoOff className="w-4 h-4" />}
              </button>

              {isMeetingActive && (
                <button
                  type="button"
                  onClick={isRecordingPaused ? handleResumeRecording : handlePauseRecording}
                  title={isRecordingPaused ? 'Resume recording' : 'Pause recording'}
                  className={`w-11 h-11 rounded-full flex items-center justify-center transition cursor-pointer ${
                    isRecordingPaused ? 'bg-amber-500 hover:bg-amber-600 text-black' : 'bg-[#3C4043] hover:bg-[#4A4E51] text-white'
                  }`}
                >
                  {isRecordingPaused ? <Play className="w-4 h-4 fill-current" /> : <Pause className="w-4 h-4" />}
                </button>
              )}

              <button
                type="button"
                onClick={handleToggleScreenShare}
                title={isScreenSharing ? 'Stop presenting' : 'Present now'}
                className={`w-11 h-11 rounded-full flex items-center justify-center transition cursor-pointer ${
                  isScreenSharing ? 'bg-[#8AB4F8] text-[#131417]' : 'bg-[#3C4043] hover:bg-[#4A4E51] text-white'
                }`}
              >
                {isScreenSharing ? <MonitorOff className="w-4 h-4" /> : <Monitor className="w-4 h-4" />}
              </button>

              <button
                type="button"
                onClick={() => setShowClosedCaptions(!showClosedCaptions)}
                title="Toggle captions"
                className={`w-11 h-11 rounded-full flex items-center justify-center transition cursor-pointer ${
                  showClosedCaptions ? 'bg-[#8AB4F8] text-[#131417]' : 'bg-[#3C4043] hover:bg-[#4A4E51] text-white'
                }`}
              >
                <Subtitles className="w-4 h-4" />
              </button>

              {/* More Options Popover */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setShowMoreMenu((prev) => !prev)}
                  title="More options"
                  className="w-11 h-11 rounded-full bg-[#3C4043] hover:bg-[#4A4E51] text-white flex items-center justify-center transition cursor-pointer"
                >
                  <MoreVertical className="w-4 h-4" />
                </button>

                {showMoreMenu && (
                  <div className="absolute bottom-14 right-0 w-52 rounded-2xl bg-[#28292D] border border-white/15 shadow-2xl p-1.5 z-30 text-xs space-y-0.5">
                    <button
                      type="button"
                      onClick={() => {
                        setShowMoreMenu(false);
                        toggleFullScreen();
                      }}
                      className="w-full px-3 py-2 rounded-xl hover:bg-white/10 text-left flex items-center gap-2 cursor-pointer"
                    >
                      {isFullScreen ? <Minimize className="w-3.5 h-3.5" /> : <Maximize className="w-3.5 h-3.5" />}
                      <span>{isFullScreen ? 'Exit Fullscreen' : 'Fullscreen'}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setShowMoreMenu(false);
                        setIsSidePanelOpen(true);
                        setSidePanelTab('diagnostics');
                        fetchDiagnostics(currentMeetingId);
                      }}
                      className="w-full px-3 py-2 rounded-xl hover:bg-white/10 text-left flex items-center gap-2 cursor-pointer"
                    >
                      <Cpu className="w-3.5 h-3.5" />
                      <span>Pipeline Diagnostics</span>
                    </button>
                    {currentMeeting && (
                      <button
                        type="button"
                        onClick={() => {
                          setShowMoreMenu(false);
                          window.open(`${api.defaults.baseURL}/meetings/${currentMeeting.meeting_id}/export-pdf`, '_blank');
                        }}
                        className="w-full px-3 py-2 rounded-xl hover:bg-white/10 text-left flex items-center gap-2 cursor-pointer"
                      >
                        <Download className="w-3.5 h-3.5" />
                        <span>Export Summary PDF</span>
                      </button>
                    )}
                    {!isMeetingActive && currentMeetingId && (
                      <>
                        <button
                          type="button"
                          onClick={() => {
                            setShowMoreMenu(false);
                            handleRetryTranscription();
                          }}
                          className="w-full px-3 py-2 rounded-xl hover:bg-white/10 text-left flex items-center gap-2 cursor-pointer"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                          <span>Retry Transcription</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setShowMoreMenu(false);
                            handleRetryAnalysis();
                          }}
                          className="w-full px-3 py-2 rounded-xl hover:bg-white/10 text-left flex items-center gap-2 cursor-pointer"
                        >
                          <Sparkles className="w-3.5 h-3.5" />
                          <span>Retry AI Analysis</span>
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>

              {!isMeetingActive ? (
                <button
                  type="button"
                  onClick={handleStartMeeting}
                  className="px-5 h-11 rounded-full bg-[#1A73E8] hover:bg-[#1557B0] text-white text-xs font-bold flex items-center gap-2 shadow-lg transition cursor-pointer"
                >
                  <Radio className="w-4 h-4" />
                  <span>Start Meeting</span>
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleEndMeeting}
                  title={isMeetingHost ? 'End & analyze meeting' : 'Leave meeting'}
                  className="px-5 h-11 rounded-full bg-[#EA4335] hover:bg-[#D93025] text-white text-xs font-bold flex items-center gap-2 shadow-lg transition cursor-pointer"
                >
                  <PhoneOff className="w-4 h-4" />
                  <span>{isMeetingHost ? 'End Meeting' : 'Leave'}</span>
                </button>
              )}
            </div>

            {/* Right: Panel Toggles (Participants, Chat, AI Assistant) */}
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  if (isSidePanelOpen && sidePanelTab === 'people') {
                    setIsSidePanelOpen(false);
                  } else {
                    setIsSidePanelOpen(true);
                    setSidePanelTab('people');
                  }
                }}
                title="Participants"
                className={`px-3 h-10 rounded-full flex items-center gap-1.5 text-xs font-semibold transition cursor-pointer ${
                  isSidePanelOpen && sidePanelTab === 'people'
                    ? 'bg-[#8AB4F8] text-[#131417]'
                    : 'bg-[#28292D] hover:bg-[#3C4043] text-white'
                }`}
              >
                <Users className="w-4 h-4" />
                <span>{remotePeers.length + 1}</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  if (isSidePanelOpen && sidePanelTab === 'chat') {
                    setIsSidePanelOpen(false);
                  } else {
                    setIsSidePanelOpen(true);
                    setSidePanelTab('chat');
                  }
                }}
                title="Meeting chat"
                className={`w-10 h-10 rounded-full flex items-center justify-center transition cursor-pointer relative ${
                  isSidePanelOpen && sidePanelTab === 'chat'
                    ? 'bg-[#8AB4F8] text-[#131417]'
                    : 'bg-[#28292D] hover:bg-[#3C4043] text-white'
                }`}
              >
                <MessageSquare className="w-4 h-4" />
                {inMeetingMessages.length > 0 && (
                  <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-[#1A73E8] text-white text-[9px] font-bold flex items-center justify-center">
                    {inMeetingMessages.length}
                  </span>
                )}
              </button>

              <button
                type="button"
                onClick={() => {
                  const isAiTab = ['transcript', 'insights', 'tasks', 'summary', 'intel'].includes(sidePanelTab);
                  if (isSidePanelOpen && isAiTab) {
                    setIsSidePanelOpen(false);
                  } else {
                    setIsSidePanelOpen(true);
                    if (!isAiTab) setSidePanelTab('transcript');
                  }
                }}
                title="AI Assistant Panel"
                className={`px-3 h-10 rounded-full flex items-center gap-1.5 text-xs font-semibold transition cursor-pointer ${
                  isSidePanelOpen && ['transcript', 'insights', 'tasks', 'summary', 'intel'].includes(sidePanelTab)
                    ? 'bg-[#8AB4F8] text-[#131417]'
                    : 'bg-[#28292D] hover:bg-[#3C4043] text-white'
                }`}
              >
                <Sparkles className="w-4 h-4" />
                <span className="hidden sm:inline">AI Panel</span>
                {extractedTasks.length > 0 && (
                  <span className="px-1.5 py-0.5 rounded-full bg-[#1A73E8] text-white text-[10px] font-bold">
                    {extractedTasks.length}
                  </span>
                )}
              </button>
            </div>
          </footer>

        </div>
      )}
    </div>
  );
}
