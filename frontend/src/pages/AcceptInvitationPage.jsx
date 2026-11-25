import React, { useState, useEffect } from 'react';
import { useParams, useSearchParams, useNavigate, Link } from 'react-router-dom';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { 
  Bot, 
  ShieldCheck, 
  CheckCircle2, 
  AlertCircle, 
  ArrowRight, 
  Lock, 
  User, 
  Briefcase,
  Users,
  Clock,
  Mail,
  Key
} from 'lucide-react';

export default function AcceptInvitationPage() {
  const { token: routeToken } = useParams();
  const [searchParams] = useSearchParams();
  const token = routeToken || searchParams.get('token');
  const navigate = useNavigate();
  const { user, login } = useAuth();

  const [invitationInfo, setInvitationInfo] = useState(null);
  const [verifying, setVerifying] = useState(true);
  const [tokenError, setTokenError] = useState('');

  const [formData, setFormData] = useState({
    name: '',
    password: '',
    confirmPassword: '',
    skills: '',
    experience: 'Intermediate',
    availability: 'Available',
    maximum_workload: 5,
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  useEffect(() => {
    if (!token) {
      setTokenError('Missing invitation token in URL.');
      setVerifying(false);
      return;
    }

    const checkToken = async () => {
      try {
        // Try validation endpoint
        const res = await api.get(`/invitations/validate/${token}`);
        if (res.data.is_valid) {
          setInvitationInfo(res.data);
          if (user?.name) {
            setFormData((prev) => ({ ...prev, name: user.name }));
          }
        } else {
          setTokenError(res.data.error || 'Invalid or expired invitation token.');
        }
      } catch (err) {
        // Fallback to legacy path if any
        try {
          const resFallback = await api.get(`/team/invitation-info?token=${token}`);
          if (resFallback.data.is_valid) {
            setInvitationInfo(resFallback.data);
          } else {
            setTokenError(resFallback.data.error || 'Invalid or expired invitation token.');
          }
        } catch (e) {
          setTokenError('Failed to verify invitation. It may have expired or already been accepted.');
        }
      } finally {
        setVerifying(false);
      }
    };

    checkToken();
  }, [token, user]);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
    setSubmitError('');
  };

  // Check email match if already logged in
  const isEmailMismatch = user && invitationInfo && (
    user.email.toLowerCase() !== (invitationInfo.invited_email || invitationInfo.email).toLowerCase()
  );

  const handleAccept = async (e) => {
    e.preventDefault();
    if (isEmailMismatch) {
      setSubmitError(`You are logged in as ${user.email}, but this invitation was sent to ${invitationInfo.invited_email || invitationInfo.email}. Please switch accounts.`);
      return;
    }

    if (!user) {
      if (!formData.name.trim()) {
        setSubmitError('Please enter your full name.');
        return;
      }
      if (formData.password !== formData.confirmPassword) {
        setSubmitError('Passwords do not match.');
        return;
      }
      if (formData.password.length < 6) {
        setSubmitError('Password must be at least 6 characters.');
        return;
      }
    }

    setSubmitting(true);
    setSubmitError('');

    try {
      const skillsArray = formData.skills
        ? formData.skills.split(',').map((s) => s.trim()).filter(Boolean)
        : [];

      const payload = {
        token: token,
        name: formData.name.trim() || user?.name || 'Team Member',
        password: formData.password || undefined,
        skills: skillsArray,
        experience: formData.experience,
        availability: formData.availability,
        maximum_workload: parseInt(formData.maximum_workload) || 5,
      };

      await api.post('/invitations/accept', payload);

      // If user wasn't logged in, login now
      if (!user) {
        await login(invitationInfo.invited_email || invitationInfo.email, formData.password);
      }

      navigate('/dashboard');
    } catch (err) {
      setSubmitError(err.response?.data?.detail || 'Failed to accept invitation.');
      setSubmitting(false);
    }
  };

  if (verifying) {
    return (
      <div className="min-h-screen bg-[#F8FAFC] flex items-center justify-center p-4">
        <div className="text-center text-xs text-[#64748B] flex items-center gap-2">
          <div className="w-5 h-5 border-2 border-[#2563EB] border-t-transparent rounded-full animate-spin" />
          <span>Verifying secure invitation token...</span>
        </div>
      </div>
    );
  }

  if (tokenError) {
    return (
      <div className="min-h-screen bg-[#F8FAFC] flex items-center justify-center p-4">
        <div className="max-w-md w-full p-8 rounded-2xl bg-white border border-rose-200 text-center space-y-4 shadow-xl">
          <div className="w-12 h-12 rounded-xl bg-rose-50 text-rose-600 mx-auto flex items-center justify-center">
            <AlertCircle className="w-6 h-6" />
          </div>
          <h3 className="text-lg font-bold text-[#0F172A]">Invitation Invalid or Expired</h3>
          <p className="text-xs text-[#64748B] leading-relaxed">{tokenError}</p>
          <div className="pt-2">
            <Link
              to="/login"
              className="inline-block px-5 py-2.5 rounded-xl bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold transition"
            >
              Return to Login
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F8FAFC] flex flex-col justify-center items-center p-4 selection:bg-[#2563EB] selection:text-white">
      <div className="max-w-lg w-full p-8 rounded-2xl bg-white border border-[#E2E8F0] shadow-xl space-y-6">
        {/* Brand */}
        <div className="flex items-center justify-center gap-2.5">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-[#2563EB] to-[#7C3AED] flex items-center justify-center shadow-md shadow-[#2563EB]/25 text-white">
            <Bot className="w-6 h-6" />
          </div>
          <h1 className="text-xl font-bold text-[#0F172A] tracking-tight">MeetMind AI</h1>
        </div>

        {/* Invitation Summary Banner */}
        <div className="p-4 rounded-xl bg-[#EFF6FF] border border-[#BFDBFE] space-y-3">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-[11px] font-semibold uppercase text-[#1E40AF]">Team Invitation</p>
              <h2 className="text-sm font-bold text-[#0F172A] mt-0.5">{invitationInfo.team_name}</h2>
            </div>
            <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${
              (invitationInfo.assigned_role || invitationInfo.role) === 'Viewer'
                ? 'bg-[#F5F3FF] text-[#7C3AED] border border-[#DDD6FE]'
                : 'bg-white text-[#2563EB] border border-[#BFDBFE]'
            }`}>
              {invitationInfo.assigned_role || invitationInfo.role} Access
            </span>
          </div>

          <div className="space-y-1 text-xs text-[#475569] pt-1 border-t border-[#BFDBFE]/60">
            <p className="flex items-center gap-1.5">
              <Mail className="w-3.5 h-3.5 text-[#2563EB]" />
              <span>Invited Email: <strong className="text-[#0F172A]">{invitationInfo.invited_email || invitationInfo.email}</strong></span>
            </p>
            {invitationInfo.invited_by && (
              <p className="flex items-center gap-1.5">
                <User className="w-3.5 h-3.5 text-[#7C3AED]" />
                <span>Invited by: <strong className="text-[#0F172A]">{invitationInfo.invited_by}</strong></span>
              </p>
            )}
            {invitationInfo.expires_at && (
              <p className="flex items-center gap-1.5 text-[11px] text-[#64748B]">
                <Clock className="w-3.5 h-3.5 text-amber-600" />
                <span>Expires: {new Date(invitationInfo.expires_at).toLocaleString()}</span>
              </p>
            )}
          </div>
        </div>

        {/* Logged in state check */}
        {user ? (
          isEmailMismatch ? (
            <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-800 space-y-2">
              <p className="font-semibold flex items-center gap-1.5">
                <AlertCircle className="w-4 h-4 text-amber-600" />
                Email Mismatch
              </p>
              <p>
                You are currently signed in as <strong>{user.email}</strong>. This invitation is bound to <strong>{invitationInfo.invited_email || invitationInfo.email}</strong>.
              </p>
              <p>Please log out and sign in with the invited email address to accept.</p>
            </div>
          ) : (
            <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
              <span>You are authenticated as <strong>{user.email}</strong>. Click below to accept and join {invitationInfo.team_name}.</span>
            </div>
          )
        ) : (
          <div className="text-xs text-[#64748B] flex items-center justify-between">
            <span>Already have an account with this email?</span>
            <Link to="/login" className="font-semibold text-[#2563EB] hover:underline">
              Log in first &rarr;
            </Link>
          </div>
        )}

        {submitError && (
          <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{submitError}</span>
          </div>
        )}

        {/* Accept Form */}
        <form onSubmit={handleAccept} className="space-y-4">
          {!user && (
            <>
              <div>
                <label className="block text-xs font-semibold text-[#475569] mb-1.5">
                  Full Name *
                </label>
                <div className="relative">
                  <User className="w-4 h-4 text-[#94A3B8] absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    required
                    name="name"
                    value={formData.name}
                    onChange={handleChange}
                    placeholder="Jane Doe"
                    className="w-full pl-9 pr-3.5 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:border-[#2563EB] transition"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-[#475569] mb-1.5">
                    Set Password *
                  </label>
                  <div className="relative">
                    <Lock className="w-4 h-4 text-[#94A3B8] absolute left-3 top-1/2 -translate-y-1/2" />
                    <input
                      type="password"
                      required
                      name="password"
                      value={formData.password}
                      onChange={handleChange}
                      placeholder="••••••••"
                      className="w-full pl-9 pr-3.5 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:border-[#2563EB] transition"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#475569] mb-1.5">
                    Confirm Password *
                  </label>
                  <div className="relative">
                    <Lock className="w-4 h-4 text-[#94A3B8] absolute left-3 top-1/2 -translate-y-1/2" />
                    <input
                      type="password"
                      required
                      name="confirmPassword"
                      value={formData.confirmPassword}
                      onChange={handleChange}
                      placeholder="••••••••"
                      className="w-full pl-9 pr-3.5 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:border-[#2563EB] transition"
                    />
                  </div>
                </div>
              </div>
            </>
          )}

          <div>
            <label className="block text-xs font-semibold text-[#475569] mb-1.5">
              Technical Skills (Comma Separated)
            </label>
            <input
              type="text"
              name="skills"
              value={formData.skills}
              onChange={handleChange}
              placeholder="React, Node.js, Python, Figma"
              className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:border-[#2563EB] transition"
            />
          </div>

          <button
            type="submit"
            disabled={submitting || isEmailMismatch}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold shadow-md transition disabled:opacity-50 cursor-pointer"
          >
            <CheckCircle2 className="w-4 h-4" />
            <span>{submitting ? 'Activating Membership...' : 'Accept Invitation & Join Team'}</span>
          </button>
        </form>
      </div>
    </div>
  );
}
