import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { 
  Users, 
  UploadCloud, 
  Mail, 
  Search, 
  Filter, 
  Eye, 
  Trash2, 
  CheckCircle2, 
  Clock, 
  Briefcase,
  Send,
  RotateCw,
  XCircle,
  AlertCircle,
  ShieldCheck,
  UserCheck
} from 'lucide-react';
import BulkImportModal from './BulkImportModal';
import InviteMemberModal from './InviteMemberModal';
import MemberProfileModal from './MemberProfileModal';

export default function TeamPage() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('members'); // 'members' | 'invitations'

  // Members state
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [availabilityFilter, setAvailabilityFilter] = useState('All');
  const [stats, setStats] = useState({ total: 0, available_count: 0, busy_count: 0 });

  // Invitations state
  const [invitations, setInvitations] = useState([]);
  const [loadingInvites, setLoadingInvites] = useState(false);
  const [invitationFilter, setInvitationFilter] = useState('All');
  const [inviteActionMsg, setInviteActionMsg] = useState('');

  // Modals state
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [isInviteModalOpen, setIsInviteModalOpen] = useState(false);
  const [selectedMember, setSelectedMember] = useState(null);
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);

  const isTeamLead = user?.role && ['lead', 'admin', 'owner', 'manager', 'team leader'].some(kw => user.role.toLowerCase().includes(kw));

  const fetchMembers = async () => {
    setLoading(true);
    try {
      const params = {};
      if (search) params.search = search;
      if (availabilityFilter !== 'All') params.availability = availabilityFilter;

      const res = await api.get('/team/members', { params });
      setMembers(res.data.members);
      setStats({
        total: res.data.total,
        available_count: res.data.available_count,
        busy_count: res.data.busy_count,
      });
    } catch (err) {
      console.error('Failed to fetch team members', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchInvitations = async () => {
    setLoadingInvites(true);
    try {
      const params = {};
      if (invitationFilter !== 'All') params.status = invitationFilter.toLowerCase();
      const res = await api.get('/team/invitations', { params });
      setInvitations(res.data || []);
    } catch (err) {
      console.error('Failed to fetch invitations', err);
    } finally {
      setLoadingInvites(false);
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchMembers();
    }, 200);
    return () => clearTimeout(timer);
  }, [search, availabilityFilter]);

  useEffect(() => {
    if (activeTab === 'invitations') {
      fetchInvitations();
    }
  }, [activeTab, invitationFilter]);

  const handleDeleteMember = async (memberId, name) => {
    if (window.confirm(`Are you sure you want to delete ${name}?`)) {
      try {
        await api.delete(`/team/members/${memberId}`);
        fetchMembers();
      } catch (err) {
        alert(err.response?.data?.detail || 'Failed to delete member.');
      }
    }
  };

  const handleRevokeInvitation = async (invitationId, email) => {
    if (!window.confirm(`Revoke pending invitation for ${email}?`)) return;
    try {
      await api.delete(`/team/invitations/${invitationId}`);
      setInviteActionMsg(`Invitation for ${email} revoked.`);
      fetchInvitations();
      setTimeout(() => setInviteActionMsg(''), 3000);
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to revoke invitation.');
    }
  };

  const handleResendInvitation = async (invitationId, email) => {
    try {
      await api.post(`/team/invitations/${invitationId}/resend`);
      setInviteActionMsg(`Invitation resent to ${email} with refreshed 72-hour token.`);
      fetchInvitations();
      setTimeout(() => setInviteActionMsg(''), 3000);
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to resend invitation.');
    }
  };

  const openProfile = (member) => {
    setSelectedMember(member);
    setIsProfileModalOpen(true);
  };

  const getStatusBadge = (status) => {
    const s = (status || 'pending').toLowerCase();
    switch (s) {
      case 'accepted':
        return (
          <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-[#ECFDF5] text-[#059669] border border-[#A7F3D0] font-semibold">
            Accepted
          </span>
        );
      case 'revoked':
        return (
          <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200 font-semibold">
            Revoked
          </span>
        );
      case 'expired':
        return (
          <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200 font-semibold">
            Expired
          </span>
        );
      default:
        return (
          <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 font-semibold">
            Pending
          </span>
        );
    }
  };

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {/* Header with Title and Invitation Actions */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-[#0F172A] tracking-tight flex items-center gap-2.5">
            <Users className="w-5 h-5 text-[#2563EB]" />
            <span>Team & Access Management</span>
          </h2>
          <p className="text-xs text-[#64748B] mt-1">
            Invite teammates with Role-Based Access Control (Editor or Viewer) and manage verified team memberships.
          </p>
        </div>

        {/* Action Buttons: Changed from direct Add Member into Invite Member */}
        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={() => setIsInviteModalOpen(true)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold shadow-sm transition cursor-pointer"
          >
            <Mail className="w-4 h-4" />
            <span>Invite Member</span>
          </button>

          <button
            onClick={() => setIsImportModalOpen(true)}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-white border border-[#E2E8F0] hover:bg-[#F8FAFC] text-[#0F172A] text-xs font-semibold shadow-sm transition cursor-pointer"
          >
            <UploadCloud className="w-4 h-4 text-[#2563EB]" />
            <span>Import CSV / Excel</span>
          </button>
        </div>
      </div>

      {inviteActionMsg && (
        <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-600" />
          <span>{inviteActionMsg}</span>
        </div>
      )}

      {/* Summary KPI Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-4 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs text-[#64748B] font-medium">Total Active Members</p>
            <p className="text-xl font-bold text-[#0F172A] mt-1">{stats.total}</p>
          </div>
          <div className="w-10 h-10 rounded-xl bg-[#EFF6FF] text-[#2563EB] flex items-center justify-center">
            <Users className="w-5 h-5" />
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs text-[#64748B] font-medium">Available for Tasks</p>
            <p className="text-xl font-bold text-[#059669] mt-1">{stats.available_count}</p>
          </div>
          <div className="w-10 h-10 rounded-xl bg-[#ECFDF5] text-[#059669] flex items-center justify-center">
            <CheckCircle2 className="w-5 h-5" />
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs text-[#64748B] font-medium">Capacity Reached</p>
            <p className="text-xl font-bold text-amber-600 mt-1">{stats.busy_count}</p>
          </div>
          <div className="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center">
            <Clock className="w-5 h-5" />
          </div>
        </div>
      </div>

      {/* Section View Tabs: Active Members vs Invitations */}
      <div className="flex border-b border-[#E2E8F0] gap-6">
        <button
          onClick={() => setActiveTab('members')}
          className={`pb-3 text-xs font-semibold flex items-center gap-2 border-b-2 -mb-px transition cursor-pointer ${
            activeTab === 'members'
              ? 'border-[#2563EB] text-[#2563EB]'
              : 'border-transparent text-[#64748B] hover:text-[#0F172A]'
          }`}
        >
          <UserCheck className="w-4 h-4" />
          <span>Active Team Members ({stats.total})</span>
        </button>

        <button
          onClick={() => setActiveTab('invitations')}
          className={`pb-3 text-xs font-semibold flex items-center gap-2 border-b-2 -mb-px transition cursor-pointer ${
            activeTab === 'invitations'
              ? 'border-[#2563EB] text-[#2563EB]'
              : 'border-transparent text-[#64748B] hover:text-[#0F172A]'
          }`}
        >
          <Mail className="w-4 h-4" />
          <span>Invitations Management</span>
        </button>
      </div>

      {activeTab === 'members' ? (
        <>
          {/* Search and Filters Bar */}
          <div className="p-4 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="relative w-full md:w-80">
              <Search className="w-4 h-4 text-[#94A3B8] absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by name, role, email, skill..."
                className="w-full pl-9 pr-4 py-2 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-xs text-[#0F172A] placeholder-[#94A3B8] focus:outline-none focus:border-[#2563EB] focus:bg-white transition"
              />
            </div>

            {/* Availability Filter Buttons */}
            <div className="flex items-center gap-2 self-start md:self-auto">
              <span className="text-xs text-[#64748B] font-medium mr-1 flex items-center gap-1">
                <Filter className="w-3.5 h-3.5" /> Availability:
              </span>
              {['All', 'Available', 'Busy', 'On Leave'].map((st) => (
                <button
                  key={st}
                  onClick={() => setAvailabilityFilter(st)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                    availabilityFilter === st
                      ? 'bg-[#2563EB] text-white shadow-sm'
                      : 'bg-[#F8FAFC] border border-[#E2E8F0] text-[#64748B] hover:text-[#0F172A]'
                  }`}
                >
                  {st}
                </button>
              ))}
            </div>
          </div>

          {/* Members Table */}
          <div className="rounded-2xl bg-white border border-[#E2E8F0] overflow-hidden shadow-sm">
            {loading ? (
              <div className="py-16 text-center text-xs text-[#64748B] flex flex-col items-center justify-center gap-3">
                <div className="w-6 h-6 border-2 border-[#2563EB] border-t-transparent rounded-full animate-spin" />
                <span>Loading MongoDB member profiles...</span>
              </div>
            ) : members.length === 0 ? (
              <div className="py-16 text-center text-xs text-[#64748B] flex flex-col items-center justify-center gap-3">
                <Users className="w-10 h-10 text-[#CBD5E1]" />
                <p className="text-sm font-semibold text-[#0F172A]">No active members found</p>
                <p className="text-xs text-[#64748B] max-w-sm">
                  Click Invite Member above to send onboarding invitation links to your team.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-[#F8FAFC] text-[#64748B] uppercase text-[11px] tracking-wider border-b border-[#E2E8F0]">
                    <tr>
                      <th className="px-5 py-3.5">Member</th>
                      <th className="px-5 py-3.5">Role / Access</th>
                      <th className="px-5 py-3.5">Technical Skills</th>
                      <th className="px-5 py-3.5">Availability</th>
                      <th className="px-5 py-3.5">Workload</th>
                      <th className="px-5 py-3.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#E2E8F0]">
                    {members.map((member) => (
                      <tr key={member.member_id} className="hover:bg-[#F8FAFC] transition">
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-3">
                            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-[#2563EB] to-[#7C3AED] flex items-center justify-center text-white font-bold text-xs uppercase flex-shrink-0 shadow-sm">
                              {member.name.slice(0, 2)}
                            </div>
                            <div>
                              <p className="font-semibold text-[#0F172A] hover:text-[#2563EB] cursor-pointer" onClick={() => openProfile(member)}>
                                {member.name}
                              </p>
                              <p className="text-[11px] text-[#64748B]">{member.email}</p>
                            </div>
                          </div>
                        </td>

                        <td className="px-5 py-4">
                          <div className="flex items-center gap-1.5 text-[#0F172A] font-medium">
                            <Briefcase className="w-3.5 h-3.5 text-[#2563EB]" />
                            <span>{member.role}</span>
                          </div>
                          <span className="text-[10px] text-[#64748B]">{member.experience}</span>
                        </td>

                        <td className="px-5 py-4 max-w-xs">
                          <div className="flex flex-wrap gap-1">
                            {member.skills && member.skills.slice(0, 3).map((skill, i) => (
                              <span
                                key={i}
                                className="px-2 py-0.5 rounded-md bg-[#EFF6FF] border border-[#BFDBFE] text-[11px] text-[#1E40AF] font-medium"
                              >
                                {skill}
                              </span>
                            ))}
                            {member.skills && member.skills.length > 3 && (
                              <span className="px-1.5 py-0.5 rounded-md bg-[#F1F5F9] text-[10px] text-[#64748B]">
                                +{member.skills.length - 3}
                              </span>
                            )}
                          </div>
                        </td>

                        <td className="px-5 py-4">
                          <div className="flex items-center gap-2">
                            <span
                              className={`w-2 h-2 rounded-full ${
                                member.availability === 'Available'
                                  ? 'bg-[#059669]'
                                  : member.availability === 'Busy'
                                  ? 'bg-amber-500'
                                  : 'bg-slate-400'
                              }`}
                            />
                            <span className="text-[#0F172A] font-medium">{member.availability}</span>
                          </div>
                        </td>

                        <td className="px-5 py-4 min-w-36">
                          <div className="flex items-center justify-between text-[11px] mb-1">
                            <span className="text-[#64748B]">{member.active_tasks_count || 0} / {member.maximum_workload || 5} tasks</span>
                            <span className="font-semibold text-[#0F172A]">{member.workload_percentage || 0}%</span>
                          </div>
                          <div className="w-full h-1.5 rounded-full bg-[#F1F5F9] overflow-hidden border border-[#E2E8F0]">
                            <div
                              className={`h-full rounded-full transition-all ${
                                (member.workload_percentage || 0) > 80
                                  ? 'bg-red-500'
                                  : (member.workload_percentage || 0) > 50
                                  ? 'bg-amber-500'
                                  : 'bg-[#059669]'
                              }`}
                              style={{ width: `${Math.min(100, member.workload_percentage || 0)}%` }}
                            />
                          </div>
                        </td>

                        <td className="px-5 py-4 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              onClick={() => openProfile(member)}
                              className="p-1.5 rounded-lg text-[#64748B] hover:text-[#2563EB] hover:bg-[#EFF6FF] transition cursor-pointer"
                              title="View Profile"
                            >
                              <Eye className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => handleDeleteMember(member.member_id, member.name)}
                              className="p-1.5 rounded-lg text-[#64748B] hover:text-red-600 hover:bg-red-50 transition cursor-pointer"
                              title="Remove Member"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      ) : (
        /* Section 7: Invitations Management Section */
        <div className="space-y-4">
          <div className="p-4 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm flex flex-col sm:flex-row items-center justify-between gap-4">
            <div>
              <h3 className="text-sm font-bold text-[#0F172A]">Team Invitations Roster</h3>
              <p className="text-xs text-[#64748B]">
                Track invitation dispatch, single-use acceptance, and token expirations.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs text-[#64748B] font-medium flex items-center gap-1">
                <Filter className="w-3.5 h-3.5" /> Status:
              </span>
              {['All', 'Pending', 'Accepted', 'Expired', 'Revoked'].map((st) => (
                <button
                  key={st}
                  onClick={() => setInvitationFilter(st)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                    invitationFilter === st
                      ? 'bg-[#2563EB] text-white shadow-sm'
                      : 'bg-[#F8FAFC] border border-[#E2E8F0] text-[#64748B] hover:text-[#0F172A]'
                  }`}
                >
                  {st}
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-2xl bg-white border border-[#E2E8F0] overflow-hidden shadow-sm">
            {loadingInvites ? (
              <div className="py-16 text-center text-xs text-[#64748B] flex flex-col items-center justify-center gap-3">
                <div className="w-6 h-6 border-2 border-[#2563EB] border-t-transparent rounded-full animate-spin" />
                <span>Loading team invitations...</span>
              </div>
            ) : invitations.length === 0 ? (
              <div className="py-16 text-center text-xs text-[#64748B] flex flex-col items-center justify-center gap-3">
                <Mail className="w-10 h-10 text-[#CBD5E1]" />
                <p className="text-sm font-semibold text-[#0F172A]">No invitations found</p>
                <p className="text-xs text-[#64748B] max-w-sm">
                  Click the Invite Member button to send an invitation email.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-[#F8FAFC] text-[#64748B] uppercase text-[11px] tracking-wider border-b border-[#E2E8F0]">
                    <tr>
                      <th className="px-5 py-3.5">Email</th>
                      <th className="px-5 py-3.5">Assigned Role</th>
                      <th className="px-5 py-3.5">Invited By</th>
                      <th className="px-5 py-3.5">Invitation Date</th>
                      <th className="px-5 py-3.5">Expiry Date</th>
                      <th className="px-5 py-3.5">Status</th>
                      <th className="px-5 py-3.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#E2E8F0]">
                    {invitations.map((inv) => (
                      <tr key={inv.invitation_id} className="hover:bg-[#F8FAFC] transition">
                        <td className="px-5 py-4 font-semibold text-[#0F172A]">
                          {inv.invited_email || inv.email}
                        </td>
                        <td className="px-5 py-4">
                          <span className={`px-2 py-0.5 rounded-md text-[11px] font-semibold ${
                            inv.assigned_role === 'Viewer'
                              ? 'bg-[#F5F3FF] text-[#7C3AED] border border-[#DDD6FE]'
                              : 'bg-[#EFF6FF] text-[#2563EB] border border-[#BFDBFE]'
                          }`}>
                            {inv.assigned_role || inv.role}
                          </span>
                        </td>
                        <td className="px-5 py-4 text-[#64748B]">
                          {inv.invited_by || 'Team Leader'}
                        </td>
                        <td className="px-5 py-4 text-[#64748B]">
                          {new Date(inv.created_at).toLocaleDateString()}
                        </td>
                        <td className="px-5 py-4 text-[#64748B]">
                          {inv.expires_at ? new Date(inv.expires_at).toLocaleString() : '72 hours'}
                        </td>
                        <td className="px-5 py-4">
                          {getStatusBadge(inv.invitation_status || inv.status)}
                        </td>
                        <td className="px-5 py-4 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            {(inv.invitation_status === 'pending' || inv.status === 'pending') && (
                              <>
                                <button
                                  type="button"
                                  onClick={() => handleResendInvitation(inv.invitation_id, inv.invited_email || inv.email)}
                                  className="px-2.5 py-1 rounded-lg bg-white border border-[#E2E8F0] hover:bg-[#F8FAFC] text-[#2563EB] font-semibold text-[11px] transition flex items-center gap-1 cursor-pointer"
                                  title="Resend invitation email"
                                >
                                  <RotateCw className="w-3 h-3" />
                                  <span>Resend</span>
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleRevokeInvitation(inv.invitation_id, inv.invited_email || inv.email)}
                                  className="px-2.5 py-1 rounded-lg bg-red-50 border border-red-200 text-red-600 hover:bg-red-100 font-semibold text-[11px] transition flex items-center gap-1 cursor-pointer"
                                  title="Revoke invitation"
                                >
                                  <XCircle className="w-3 h-3" />
                                  <span>Revoke</span>
                                </button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modals */}
      <BulkImportModal
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
        onImportCompleted={() => {
          fetchMembers();
          if (activeTab === 'invitations') fetchInvitations();
        }}
      />

      <InviteMemberModal
        isOpen={isInviteModalOpen}
        onClose={() => setIsInviteModalOpen(false)}
        onInvitationCreated={() => {
          if (activeTab === 'invitations') fetchInvitations();
        }}
      />

      <MemberProfileModal
        isOpen={isProfileModalOpen}
        onClose={() => setIsProfileModalOpen(false)}
        member={selectedMember}
        onMemberUpdated={fetchMembers}
        onMemberDeleted={fetchMembers}
      />
    </div>
  );
}
