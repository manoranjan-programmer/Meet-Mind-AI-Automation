import React, { useState, useEffect, useRef } from 'react';
import { 
  Send, 
  Smile, 
  Paperclip, 
  Search, 
  MoreVertical, 
  Users, 
  Check, 
  CheckCheck, 
  Clock, 
  Edit3, 
  Trash2, 
  X, 
  ShieldCheck,
  UserCheck,
  Sparkles,
  AlertCircle
} from 'lucide-react';
import api, { getWebSocketUrl } from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function WorkspaceChatPage() {
  const { user } = useAuth();
  const teamId = user?.team_id || 'team_default';

  // Chat state
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  const [members, setMembers] = useState([]);
  const [onlineCount, setOnlineCount] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [showSearch, setShowSearch] = useState(false);
  const [showMembersList, setShowMembersList] = useState(false);
  const [typingUsers, setTypingUsers] = useState(new Set());
  const [wsConnected, setWsConnected] = useState(false);
  const [editingMessage, setEditingMessage] = useState(null);
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  const messagesEndRef = useRef(null);
  const wsRef = useRef(null);
  const typingTimeoutRef = useRef(null);

  const quickEmojis = ['👍', '❤️', '👏', '🎉', '🚀', '🔥', '💡', '✅', '🙏', '😊'];

  // Scroll to bottom on new message
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, typingUsers]);

  // Load message history and active members
  useEffect(() => {
    fetchChatHistory();
    fetchChatMembers();
  }, [teamId]);

  const fetchChatHistory = async () => {
    setIsLoading(true);
    try {
      const res = await api.get(`/workspaces/${teamId}/chat/messages?limit=100`);
      setMessages(res.data?.messages || []);
    } catch (err) {
      console.error('Failed to load chat history:', err);
      setErrorMessage('Could not load workspace chat messages.');
    } finally {
      setIsLoading(false);
    }
  };

  const fetchChatMembers = async () => {
    try {
      const res = await api.get(`/workspaces/${teamId}/chat/members`);
      setMembers(res.data?.members || []);
      setOnlineCount(res.data?.online_count || 1);
    } catch (err) {
      console.error('Failed to load chat members:', err);
    }
  };

  // WebSocket Connection Lifecycle
  useEffect(() => {
    const token = localStorage.getItem('meetmind_token');
    if (!token) return;

    let isMounted = true;
    let reconnectTimeout = null;

    const connectWs = () => {
      try {
        const wsUrl = `${getWebSocketUrl(`/ws/workspaces/${teamId}/chat`)}?token=${encodeURIComponent(token)}`;
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          if (!isMounted) return;
          setWsConnected(true);
          console.log('[WorkspaceChat WS] Connected successfully.');
          // Mark messages as read
          ws.send(JSON.stringify({ event: 'mark_read', data: {} }));
        };

        ws.onmessage = (event) => {
          if (!isMounted) return;
          try {
            const parsed = JSON.parse(event.data);
            handleWsEvent(parsed.event, parsed.data);
          } catch (e) {
            console.error('[WorkspaceChat WS] Parse error:', e);
          }
        };

        ws.onclose = () => {
          if (!isMounted) return;
          setWsConnected(false);
          console.log('[WorkspaceChat WS] Disconnected. Reconnecting in 3s...');
          reconnectTimeout = setTimeout(connectWs, 3000);
        };

        ws.onerror = (err) => {
          console.error('[WorkspaceChat WS] Error:', err);
          ws.close();
        };
      } catch (err) {
        console.error('[WorkspaceChat WS] Initialization failed:', err);
      }
    };

    connectWs();

    return () => {
      isMounted = false;
      clearTimeout(reconnectTimeout);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [teamId]);

  const handleWsEvent = (eventName, data) => {
    if (eventName === 'message_created') {
      setMessages((prev) => {
        // Prevent duplicate append
        if (prev.some((m) => m.message_id === data.message_id)) return prev;
        return [...prev, data];
      });
      // Clear typing indicator for sender
      setTypingUsers((prev) => {
        const next = new Set(prev);
        next.delete(data.sender_name);
        return next;
      });
    } else if (eventName === 'message_edited') {
      setMessages((prev) =>
        prev.map((m) => (m.message_id === data.message_id ? data : m))
      );
    } else if (eventName === 'message_deleted') {
      setMessages((prev) => prev.filter((m) => m.message_id !== data.message_id));
    } else if (eventName === 'member_online') {
      fetchChatMembers();
    } else if (eventName === 'member_offline') {
      fetchChatMembers();
    } else if (eventName === 'typing') {
      if (data.is_typing && data.name) {
        setTypingUsers((prev) => new Set([...prev, data.name]));
        setTimeout(() => {
          setTypingUsers((prev) => {
            const next = new Set(prev);
            next.delete(data.name);
            return next;
          });
        }, 3000);
      }
    }
  };

  // Send message
  const handleSendMessage = async (e) => {
    e?.preventDefault();
    if (!inputText.trim()) return;

    const content = inputText.trim();
    setInputText('');
    setShowEmojiPicker(false);

    // Try WebSocket send first for instant responsiveness
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        event: 'send_message',
        data: { content }
      }));
    } else {
      // Fallback to HTTP POST
      try {
        const res = await api.post(`/workspaces/${teamId}/chat/messages`, { content });
        setMessages((prev) => [...prev, res.data]);
      } catch (err) {
        console.error('Failed to send message:', err);
        setErrorMessage('Failed to send message.');
      }
    }
  };

  // Handle typing notification
  const handleInputChange = (e) => {
    setInputText(e.target.value);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      clearTimeout(typingTimeoutRef.current);
      wsRef.current.send(JSON.stringify({
        event: 'typing',
        data: { is_typing: true }
      }));
      typingTimeoutRef.current = setTimeout(() => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({
            event: 'typing',
            data: { is_typing: false }
          }));
        }
      }, 2500);
    }
  };

  // Edit message
  const handleSaveEdit = async () => {
    if (!editingMessage || !editingMessage.content.trim()) return;
    try {
      await api.patch(`/workspaces/${teamId}/chat/messages/${editingMessage.message_id}`, {
        content: editingMessage.content.trim()
      });
      setEditingMessage(null);
    } catch (err) {
      alert('Failed to edit message: ' + (err.response?.data?.detail || err.message));
    }
  };

  // Delete message
  const handleDeleteMessage = async (messageId) => {
    if (!window.confirm('Delete this message for everyone in the workspace?')) return;
    try {
      await api.delete(`/workspaces/${teamId}/chat/messages/${messageId}`);
    } catch (err) {
      alert('Failed to delete message: ' + (err.response?.data?.detail || err.message));
    }
  };

  // Filter messages by search
  const displayedMessages = messages.filter((m) =>
    searchTerm.trim() === '' || m.content.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const formatMessageTime = (dateStr) => {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const formatMessageDate = (dateStr) => {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    const today = new Date();
    if (d.toDateString() === today.toDateString()) return 'Today';
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
    return d.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
  };

  const getInitials = (name) => {
    if (!name) return 'MM';
    return name.split(' ').map((n) => n[0]).join('').toUpperCase().substring(0, 2);
  };

  return (
    <div className="h-[calc(100vh-5rem)] flex flex-col rounded-2xl bg-white border border-[#E2E8F0] shadow-sm overflow-hidden animate-fade-in">
      
      {/* Top Header: WhatsApp Style Workspace Header */}
      <div className="px-5 py-3.5 bg-[#F8FAFC] border-b border-[#E2E8F0] flex items-center justify-between z-10">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-[#2563EB] to-[#7C3AED] text-white flex items-center justify-center font-bold text-sm shadow-xs">
            {getInitials(user?.team_name || teamId)}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-[#0F172A] tracking-tight">
                {user?.team_name || 'Workspace Team'} Chat
              </h2>
              <span className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-emerald-500' : 'bg-amber-400'} animate-pulse`} />
            </div>
            <p className="text-[11px] text-[#64748B]">
              {members.length} members • {onlineCount} online
              {typingUsers.size > 0 && (
                <span className="text-[#059669] font-semibold ml-2 animate-pulse">
                  {Array.from(typingUsers).join(', ')} typing...
                </span>
              )}
            </p>
          </div>
        </div>

        {/* Right actions */}
        <div className="flex items-center gap-2">
          {showSearch ? (
            <div className="relative flex items-center">
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search messages..."
                className="pl-8 pr-3 py-1.5 rounded-lg bg-white border border-[#CBD5E1] text-xs font-medium text-[#0F172A] focus:border-[#2563EB] w-48 sm:w-64"
                autoFocus
              />
              <Search className="w-3.5 h-3.5 text-[#94A3B8] absolute left-2.5" />
              <button onClick={() => { setShowSearch(false); setSearchTerm(''); }} className="p-1 text-[#64748B] hover:text-[#0F172A] ml-1">
                <X className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowSearch(true)}
              title="Search conversation"
              className="p-2 rounded-lg text-[#64748B] hover:text-[#0F172A] hover:bg-[#F1F5F9] transition cursor-pointer"
            >
              <Search className="w-4 h-4" />
            </button>
          )}

          <button
            onClick={() => setShowMembersList(!showMembersList)}
            title="View workspace members"
            className={`p-2 rounded-lg transition cursor-pointer flex items-center gap-1.5 text-xs font-medium ${
              showMembersList
                ? 'bg-[#EFF6FF] text-[#2563EB] border border-[#BFDBFE]'
                : 'text-[#64748B] hover:text-[#0F172A] hover:bg-[#F1F5F9]'
            }`}
          >
            <Users className="w-4 h-4" />
            <span className="hidden sm:inline">Members</span>
          </button>
        </div>
      </div>

      {/* Main Chat Workspace Body */}
      <div className="flex-1 flex overflow-hidden relative">
        
        {/* Messages Stream Container */}
        <div className="flex-1 flex flex-col bg-[#F8FAFC]/50 overflow-y-auto p-4 sm:p-6 space-y-3">
          
          {isLoading ? (
            <div className="flex-1 flex items-center justify-center text-xs text-[#64748B]">
              <div className="w-5 h-5 border-2 border-[#2563EB] border-t-transparent rounded-full animate-spin mr-2" />
              Loading workspace chat history...
            </div>
          ) : displayedMessages.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center text-center p-6 space-y-2 text-[#64748B]">
              <div className="w-12 h-12 rounded-2xl bg-[#EFF6FF] text-[#2563EB] flex items-center justify-center">
                <Users className="w-6 h-6" />
              </div>
              <h4 className="text-xs font-bold text-[#0F172A]">Welcome to your private Workspace Chat!</h4>
              <p className="text-[11px] max-w-sm">
                This is a secure group conversation for your team. Send messages, collaborate on tasks, and share updates in real-time.
              </p>
            </div>
          ) : (
            displayedMessages.map((msg, idx) => {
              const isMe = msg.sender_id === user?.user_id || msg.sender_email === user?.email;
              const prevMsg = displayedMessages[idx - 1];
              const showDate = !prevMsg || formatMessageDate(prevMsg.created_at) !== formatMessageDate(msg.created_at);

              return (
                <React.Fragment key={msg.message_id || idx}>
                  {/* Date Separator Pill */}
                  {showDate && (
                    <div className="flex justify-center my-2">
                      <span className="px-3 py-1 rounded-full bg-white border border-[#E2E8F0] shadow-2xs text-[10px] font-semibold text-[#64748B]">
                        {formatMessageDate(msg.created_at)}
                      </span>
                    </div>
                  )}

                  {/* Message Bubble */}
                  <div className={`flex items-end gap-2 group ${isMe ? 'justify-end' : 'justify-start'}`}>
                    
                    {/* Other sender's avatar */}
                    {!isMe && (
                      <div className="w-7 h-7 rounded-full bg-[#1A73E8] text-white flex items-center justify-center text-[10px] font-bold flex-shrink-0 shadow-xs mb-1">
                        {getInitials(msg.sender_name)}
                      </div>
                    )}

                    {/* Bubble Card */}
                    <div className={`relative max-w-[85%] sm:max-w-md px-3.5 py-2 rounded-2xl shadow-2xs text-xs space-y-1 ${
                      isMe 
                        ? 'bg-[#EFF6FF] text-[#0F172A] border border-[#BFDBFE] rounded-br-xs' 
                        : 'bg-white text-[#0F172A] border border-[#E2E8F0] rounded-bl-xs'
                    }`}>
                      
                      {/* Sender name for received messages */}
                      {!isMe && (
                        <div className="flex items-center gap-1.5 pb-0.5">
                          <span className="font-bold text-[11px] text-[#2563EB]">{msg.sender_name}</span>
                          <span className="text-[9px] px-1.5 py-0.2 rounded bg-[#F1F5F9] text-[#64748B] font-medium">
                            {msg.sender_role || 'Member'}
                          </span>
                        </div>
                      )}

                      {/* Content */}
                      <p className="leading-relaxed whitespace-pre-wrap break-words">{msg.content}</p>

                      {/* Meta Footer: Timestamp, Edited badge, Read checkmark */}
                      <div className="flex items-center justify-end gap-1.5 text-[9px] text-[#94A3B8] pt-0.5">
                        {msg.is_edited && <span className="italic">edited</span>}
                        <span>{formatMessageTime(msg.created_at)}</span>
                        {isMe && (
                          <span title="Read by workspace members">
                            <CheckCheck className="w-3.5 h-3.5 text-[#2563EB]" />
                          </span>
                        )}
                      </div>

                      {/* Hover action menu for editing / deleting */}
                      {(isMe || user?.role === 'Team Leader') && (
                        <div className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity bg-white/95 rounded-md shadow-xs border border-[#CBD5E1] flex items-center p-0.5">
                          {isMe && (
                            <button
                              onClick={() => setEditingMessage(msg)}
                              title="Edit message"
                              className="p-1 hover:bg-[#F1F5F9] rounded text-[#64748B] hover:text-[#2563EB]"
                            >
                              <Edit3 className="w-3 h-3" />
                            </button>
                          )}
                          <button
                            onClick={() => handleDeleteMessage(msg.message_id)}
                            title="Delete message"
                            className="p-1 hover:bg-rose-50 rounded text-[#64748B] hover:text-rose-600"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                      )}

                    </div>
                  </div>
                </React.Fragment>
              );
            })
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Right Side Member List Drawer */}
        {showMembersList && (
          <div className="w-64 bg-white border-l border-[#E2E8F0] p-4 flex flex-col space-y-3 z-10 animate-fade-in">
            <div className="flex items-center justify-between pb-2 border-b border-[#E2E8F0]">
              <span className="text-xs font-bold text-[#0F172A]">Workspace Members ({members.length})</span>
              <button onClick={() => setShowMembersList(false)} className="p-1 hover:bg-[#F1F5F9] rounded text-[#64748B]">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-2">
              {members.map((m) => (
                <div key={m.member_id} className="p-2 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="relative">
                      <div className="w-7 h-7 rounded-full bg-[#2563EB] text-white flex items-center justify-center text-[10px] font-bold">
                        {getInitials(m.name)}
                      </div>
                      <span className={`w-2 h-2 rounded-full absolute bottom-0 right-0 border border-white ${
                        m.is_online ? 'bg-emerald-500' : 'bg-slate-300'
                      }`} />
                    </div>
                    <div className="min-w-0">
                      <span className="font-semibold text-[#0F172A] block truncate">{m.name}</span>
                      <span className="text-[10px] text-[#64748B] block truncate">{m.role}</span>
                    </div>
                  </div>
                  <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                    m.is_online ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'
                  }`}>
                    {m.is_online ? 'Online' : 'Offline'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

      </div>

      {/* Quick Emoji Bar */}
      {showEmojiPicker && (
        <div className="px-5 py-2 bg-white border-t border-[#E2E8F0] flex items-center gap-2 animate-fade-in overflow-x-auto">
          {quickEmojis.map((emoji) => (
            <button
              key={emoji}
              type="button"
              onClick={() => setInputText((prev) => prev + emoji)}
              className="text-lg p-1 hover:scale-125 transition-transform cursor-pointer"
            >
              {emoji}
            </button>
          ))}
        </div>
      )}

      {/* Bottom Message Input Bar */}
      <form onSubmit={handleSendMessage} className="p-3 bg-white border-t border-[#E2E8F0] flex items-center gap-2">
        <button
          type="button"
          onClick={() => setShowEmojiPicker(!showEmojiPicker)}
          title="Add emoji"
          className="p-2 rounded-xl hover:bg-[#F1F5F9] text-[#64748B] hover:text-[#0F172A] transition cursor-pointer"
        >
          <Smile className="w-5 h-5" />
        </button>

        <input
          type="text"
          value={inputText}
          onChange={handleInputChange}
          placeholder="Type a message to your workspace team..."
          className="flex-1 px-4 py-2.5 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1] text-xs font-medium text-[#0F172A] focus:bg-white focus:border-[#2563EB] transition"
        />

        <button
          type="submit"
          disabled={!inputText.trim()}
          className="p-2.5 rounded-xl bg-[#2563EB] hover:bg-[#1D4ED8] text-white shadow-xs transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Send className="w-4 h-4" />
        </button>
      </form>

      {/* Edit Message Modal */}
      {editingMessage && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-[#E2E8F0] shadow-xl w-full max-w-md p-5 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-[#E2E8F0]">
              <h3 className="text-sm font-bold text-[#0F172A]">Edit Message</h3>
              <button onClick={() => setEditingMessage(null)} className="p-1 hover:bg-[#F1F5F9] rounded text-[#64748B]">
                <X className="w-4 h-4" />
              </button>
            </div>

            <textarea
              value={editingMessage.content}
              onChange={(e) => setEditingMessage({ ...editingMessage, content: e.target.value })}
              rows={3}
              className="w-full px-3 py-2 rounded-xl bg-[#F8FAFC] border border-[#CBD5E1] text-xs text-[#0F172A] focus:bg-white focus:border-[#2563EB]"
            />

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-[#E2E8F0]">
              <button
                type="button"
                onClick={() => setEditingMessage(null)}
                className="px-3.5 py-1.5 rounded-xl border border-[#CBD5E1] text-xs font-semibold text-[#64748B]"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveEdit}
                className="px-4 py-1.5 rounded-xl bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold shadow-xs"
              >
                Save Edit
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
