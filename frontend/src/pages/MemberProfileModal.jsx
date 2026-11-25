import React, { useState } from 'react';
import Modal from '../components/Modal';
import api from '../services/api';
import { 
  Briefcase, 
  Award, 
  Activity, 
  Edit3, 
  Save, 
  Trash2 
} from 'lucide-react';

export default function MemberProfileModal({ isOpen, onClose, member, onMemberUpdated, onMemberDeleted }) {
  const [isEditing, setIsEditing] = useState(false);
  const [editData, setEditData] = useState({
    name: '',
    role: '',
    skills: '',
    experience: 'Intermediate',
    availability: 'Available',
    maximum_workload: 5,
  });
  const [loading, setLoading] = useState(false);

  React.useEffect(() => {
    if (member) {
      setEditData({
        name: member.name || '',
        role: member.role || '',
        skills: Array.isArray(member.skills) ? member.skills.join(', ') : '',
        experience: member.experience || 'Intermediate',
        availability: member.availability || 'Available',
        maximum_workload: member.maximum_workload || 5,
      });
      setIsEditing(false);
    }
  }, [member]);

  if (!member) return null;

  const handleSave = async () => {
    setLoading(true);
    try {
      const skillsArray = editData.skills
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);

      await api.put(`/team/members/${member.member_id}`, {
        name: editData.name,
        role: editData.role,
        skills: skillsArray,
        experience: editData.experience,
        availability: editData.availability,
        maximum_workload: parseInt(editData.maximum_workload),
      });

      onMemberUpdated();
      setIsEditing(false);
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to update member.');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (window.confirm(`Are you sure you want to remove ${member.name} from the team?`)) {
      try {
        await api.delete(`/team/members/${member.member_id}`);
        onMemberDeleted();
        onClose();
      } catch (err) {
        alert(err.response?.data?.detail || 'Failed to delete member.');
      }
    }
  };

  const getMethodBadge = (method) => {
    switch (method) {
      case 'csv_import':
        return <span className="text-[11px] px-2 py-0.5 rounded-md bg-[#EFF6FF] text-[#2563EB] border border-[#BFDBFE] font-medium">CSV Import</span>;
      case 'invitation':
        return <span className="text-[11px] px-2 py-0.5 rounded-md bg-[#F5F3FF] text-[#7C3AED] border border-[#DDD6FE] font-medium">Invited Member</span>;
      default:
        return <span className="text-[11px] px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium">Manual Admin</span>;
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditing ? 'Edit Member Profile' : `${member.name}'s Profile`}
      subtitle={`Member ID: ${member.member_id} • Team Profile`}
      maxWidth="max-w-2xl"
    >
      <div className="space-y-6">
        {/* Profile Card Header */}
        <div className="p-4 rounded-2xl bg-[#F8FAFC] border border-[#E2E8F0] flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-[#2563EB] to-[#7C3AED] flex items-center justify-center text-white text-xl font-bold uppercase shadow-sm">
              {member.name.slice(0, 2)}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h4 className="text-base font-bold text-[#0F172A]">{member.name}</h4>
                {getMethodBadge(member.registration_method)}
              </div>
              <p className="text-xs text-[#2563EB] font-mono mt-0.5">{member.email}</p>
              <div className="flex items-center gap-2 mt-1.5">
                <span className={`inline-block w-2 h-2 rounded-full ${
                  member.availability === 'Available' ? 'bg-[#059669]' : member.availability === 'Busy' ? 'bg-amber-500' : 'bg-slate-400'
                }`} />
                <span className="text-xs text-[#64748B]">{member.availability}</span>
              </div>
            </div>
          </div>

          <div className="flex gap-2">
            {!isEditing ? (
              <>
                <button
                  onClick={() => setIsEditing(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-[#E2E8F0] text-[#64748B] hover:text-[#0F172A] hover:bg-[#F8FAFC] text-xs font-semibold transition cursor-pointer"
                >
                  <Edit3 className="w-3.5 h-3.5" />
                  <span>Edit</span>
                </button>
                <button
                  onClick={handleDelete}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-50 border border-red-200 text-red-600 hover:bg-red-100 text-xs font-semibold transition cursor-pointer"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </>
            ) : (
              <button
                onClick={handleSave}
                disabled={loading}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-[#059669] hover:bg-[#047857] text-white text-xs font-semibold shadow-sm transition cursor-pointer"
              >
                <Save className="w-3.5 h-3.5" />
                <span>Save</span>
              </button>
            )}
          </div>
        </div>

        {/* Edit View */}
        {isEditing ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-[#475569] mb-1">Full Name</label>
                <input
                  type="text"
                  value={editData.name}
                  onChange={(e) => setEditData({ ...editData, name: e.target.value })}
                  className="w-full px-3 py-2 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:border-[#2563EB]"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-[#475569] mb-1">Job Role</label>
                <input
                  type="text"
                  value={editData.role}
                  onChange={(e) => setEditData({ ...editData, role: e.target.value })}
                  className="w-full px-3 py-2 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:border-[#2563EB]"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-[#475569] mb-1">Technical Skills</label>
              <input
                type="text"
                value={editData.skills}
                onChange={(e) => setEditData({ ...editData, skills: e.target.value })}
                className="w-full px-3 py-2 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:border-[#2563EB]"
              />
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-semibold text-[#475569] mb-1">Experience</label>
                <select
                  value={editData.experience}
                  onChange={(e) => setEditData({ ...editData, experience: e.target.value })}
                  className="w-full px-3 py-2 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs"
                >
                  <option value="Junior">Junior</option>
                  <option value="Intermediate">Intermediate</option>
                  <option value="Senior">Senior</option>
                  <option value="Advanced">Advanced</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-[#475569] mb-1">Availability</label>
                <select
                  value={editData.availability}
                  onChange={(e) => setEditData({ ...editData, availability: e.target.value })}
                  className="w-full px-3 py-2 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs"
                >
                  <option value="Available">Available</option>
                  <option value="Busy">Busy</option>
                  <option value="On Leave">On Leave</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-[#475569] mb-1">Max Workload</label>
                <input
                  type="number"
                  min="1"
                  max="20"
                  value={editData.maximum_workload}
                  onChange={(e) => setEditData({ ...editData, maximum_workload: e.target.value })}
                  className="w-full px-3 py-2 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs"
                />
              </div>
            </div>
          </div>
        ) : (
          /* View Profile Details */
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="p-3.5 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0]">
                <div className="flex items-center gap-2 text-xs text-[#64748B] mb-1">
                  <Briefcase className="w-3.5 h-3.5 text-[#2563EB]" />
                  <span>Job Role</span>
                </div>
                <p className="text-sm font-semibold text-[#0F172A]">{member.role}</p>
              </div>

              <div className="p-3.5 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0]">
                <div className="flex items-center gap-2 text-xs text-[#64748B] mb-1">
                  <Award className="w-3.5 h-3.5 text-[#7C3AED]" />
                  <span>Experience Level</span>
                </div>
                <p className="text-sm font-semibold text-[#0F172A]">{member.experience}</p>
              </div>
            </div>

            {/* Workload Progress Card */}
            <div className="p-4 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0]">
              <div className="flex items-center justify-between text-xs mb-2">
                <span className="text-[#64748B] font-medium flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5 text-[#2563EB]" /> Workload Capacity
                </span>
                <span className="text-[#0F172A] font-semibold">
                  {member.active_tasks_count || 0} / {member.maximum_workload || 5} active tasks ({member.workload_percentage || 0}%)
                </span>
              </div>
              <div className="w-full h-2 rounded-full bg-[#E2E8F0] overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    (member.workload_percentage || 0) > 80
                      ? 'bg-red-500'
                      : (member.workload_percentage || 0) > 50
                      ? 'bg-amber-500'
                      : 'bg-[#059669]'
                  }`}
                  style={{ width: `${Math.min(100, member.workload_percentage || 0)}%` }}
                />
              </div>
            </div>

            {/* Technical Skills */}
            <div className="p-4 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0]">
              <h5 className="text-xs font-semibold text-[#475569] mb-2.5">
                Technical Skills (LangGraph AI Assignment Matching)
              </h5>
              <div className="flex flex-wrap gap-1.5">
                {member.skills && member.skills.length > 0 ? (
                  member.skills.map((skill, index) => (
                    <span
                      key={index}
                      className="px-2.5 py-1 rounded-lg bg-[#EFF6FF] border border-[#BFDBFE] text-xs text-[#1E40AF] font-medium"
                    >
                      {skill}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-[#64748B]">No technical skills listed.</span>
                )}
              </div>
            </div>

            {/* Registration Dossier */}
            <div className="p-3.5 rounded-xl bg-[#F1F5F9] border border-[#E2E8F0] flex items-center justify-between text-xs">
              <span className="text-[#64748B]">Database Persistence:</span>
              <span className="text-[#0F172A] font-mono font-medium">
                Method: {member.registration_method} • Status: {member.account_status}
              </span>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
