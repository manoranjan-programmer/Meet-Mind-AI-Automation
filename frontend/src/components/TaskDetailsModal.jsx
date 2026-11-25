import React, { useState, useEffect } from 'react';
import Modal from './Modal';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { 
  Calendar, 
  Tag, 
  AlertCircle, 
  CheckCircle2, 
  Trash2, 
  Edit3, 
  Save, 
  Clock, 
  Zap,
  ShieldCheck,
  CheckSquare
} from 'lucide-react';

const STATUS_OPTIONS = ['To Do', 'In Progress', 'Review', 'Completed'];
const PRIORITY_OPTIONS = ['Low', 'Medium', 'High', 'Critical'];

export default function TaskDetailsModal({ 
  isOpen, 
  onClose, 
  task, 
  onTaskUpdated, 
  onTaskDeleted,
  teamMembers = [] 
}) {
  const { user } = useAuth();
  const [isEditing, setIsEditing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const [formData, setFormData] = useState({
    title: '',
    description: '',
    priority: 'Medium',
    status: 'To Do',
    deadline: '',
    meeting_title: '',
    assigned_member_id: '',
  });

  const isAdmin = user?.role?.toLowerCase().includes('admin') || 
                  user?.role?.toLowerCase().includes('lead') || 
                  user?.role?.toLowerCase().includes('manager');
  const canCompleteTask = !isAdmin && task?.approval_status?.toLowerCase() === 'approved' && (
    task?.assigned_member_id === user?.user_id ||
    (task?.assigned_member_email || '').toLowerCase() === (user?.email || '').toLowerCase()
  );

  useEffect(() => {
    if (task) {
      setFormData({
        title: task.title || '',
        description: task.description || '',
        priority: task.priority || 'Medium',
        status: task.status || 'To Do',
        deadline: task.deadline || '',
        meeting_title: task.meeting_title || 'General',
        assigned_member_id: task.assigned_member_id || '',
      });
      setIsEditing(false);
      setError('');
      setSuccess('');
    }
  }, [task]);

  if (!task) return null;

  const handleStatusChange = async (newStatus) => {
    setLoading(true);
    setError('');
    try {
      await api.patch(`/tasks/${task.task_id}/status`, { status: newStatus });
      setFormData((prev) => ({ ...prev, status: newStatus }));
      onTaskUpdated();
      setSuccess(`Status moved to "${newStatus}"`);
      setTimeout(() => setSuccess(''), 2000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update status.');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveEdits = async () => {
    setLoading(true);
    setError('');
    try {
      await api.patch(`/tasks/${task.task_id}`, {
        title: formData.title.trim(),
        description: formData.description.trim(),
        priority: formData.priority,
        status: formData.status,
        deadline: formData.deadline.trim() || null,
        meeting_title: formData.meeting_title.trim(),
        assigned_member_id: formData.assigned_member_id || null,
      });
      onTaskUpdated();
      setIsEditing(false);
      setSuccess('Task details updated successfully.');
      setTimeout(() => setSuccess(''), 2000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save changes.');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (window.confirm(`Delete task "${task.title}" (${task.task_id}) permanently?`)) {
      setLoading(true);
      try {
        await api.delete(`/tasks/${task.task_id}`);
        onTaskDeleted();
        onClose();
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to delete task.');
        setLoading(false);
      }
    }
  };

  const getPriorityBadge = (priority) => {
    switch (priority) {
      case 'Critical':
        return 'bg-red-50 text-red-700 border-red-200';
      case 'High':
        return 'bg-amber-50 text-amber-700 border-amber-200';
      case 'Medium':
        return 'bg-[#EFF6FF] text-[#2563EB] border-[#BFDBFE]';
      default:
        return 'bg-slate-50 text-slate-700 border-slate-200';
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'Completed':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200';
      case 'Review':
        return 'bg-[#F5F3FF] text-[#7C3AED] border-[#DDD6FE]';
      case 'In Progress':
        return 'bg-[#EFF6FF] text-[#2563EB] border-[#BFDBFE]';
      default:
        return 'bg-amber-50 text-amber-700 border-amber-200';
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditing ? 'Edit Task Details' : task.title}
      subtitle={`Task ID: ${task.task_id} • Meeting: ${task.meeting_title || 'General Meeting'}`}
      maxWidth="max-w-2xl"
    >
      <div className="space-y-6">
        {error && (
          <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {success && (
          <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
            <span>{success}</span>
          </div>
        )}

        {/* Status Transition Bar */}
        <div className="p-4 rounded-2xl bg-[#F8FAFC] border border-[#E2E8F0] space-y-2.5">
          <div className="flex items-center justify-between text-xs">
            <span className="text-[#64748B] font-medium flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-[#2563EB]" /> Current Status:
            </span>
            <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${getStatusBadge(formData.status)}`}>
              {formData.status}
            </span>
          </div>

          <div className="grid grid-cols-4 gap-2 pt-1">
            {STATUS_OPTIONS.filter((st) => st !== 'Completed' || canCompleteTask).map((st) => (
              <button
                key={st}
                type="button"
                onClick={() => handleStatusChange(st)}
                disabled={loading || formData.status === st}
                className={`py-2 px-2 rounded-xl text-xs font-semibold transition text-center cursor-pointer border ${
                  formData.status === st
                    ? 'bg-[#2563EB] text-white border-[#2563EB] shadow-xs'
                    : 'bg-white text-[#64748B] hover:text-[#0F172A] border-[#E2E8F0] hover:bg-[#F8FAFC]'
                }`}
              >
                {st}
              </button>
            ))}
          </div>
        </div>

        {/* View vs Edit Body */}
        {isEditing ? (
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-[#475569] mb-1">Task Title *</label>
              <input
                type="text"
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:border-[#2563EB] transition"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-[#475569] mb-1">Description</label>
              <textarea
                rows={4}
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:border-[#2563EB] transition"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-[#475569] mb-1">Priority</label>
                <select
                  value={formData.priority}
                  onChange={(e) => setFormData({ ...formData, priority: e.target.value })}
                  className="w-full px-3 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs"
                >
                  {PRIORITY_OPTIONS.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#475569] mb-1">Deadline</label>
                <input
                  type="date"
                  value={formData.deadline}
                  onChange={(e) => setFormData({ ...formData, deadline: e.target.value })}
                  className="w-full px-3 py-2 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-[#475569] mb-1">Meeting Title</label>
                <input
                  type="text"
                  value={formData.meeting_title}
                  onChange={(e) => setFormData({ ...formData, meeting_title: e.target.value })}
                  className="w-full px-3 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#475569] mb-1">Assign Team Member</label>
                <select
                  value={formData.assigned_member_id}
                  onChange={(e) => setFormData({ ...formData, assigned_member_id: e.target.value })}
                  className="w-full px-3 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs"
                >
                  <option value="">Unassigned</option>
                  {teamMembers.map((m) => (
                    <option key={m.member_id} value={m.member_id}>
                      {m.name} ({m.role}) - {m.availability}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Metadata Tags Strip */}
            <div className="flex flex-wrap items-center gap-2">
              <span className={`px-2.5 py-1 rounded-lg text-xs font-semibold border ${getPriorityBadge(task.priority)}`}>
                {task.priority} Priority
              </span>
              <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#F8FAFC] border border-[#E2E8F0] text-xs text-[#64748B]">
                <Calendar className="w-3.5 h-3.5 text-[#2563EB]" />
                <span>{task.deadline || 'No deadline'}</span>
              </span>
              <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#F8FAFC] border border-[#E2E8F0] text-xs text-[#7C3AED]">
                <Tag className="w-3.5 h-3.5" />
                <span>{task.meeting_title || 'General Meeting'}</span>
              </span>
              <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-700">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>{task.approval_status || 'Approved'}</span>
              </span>
            </div>

            {/* Description */}
            <div className="p-4 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] space-y-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-[#64748B]">
                Task Description
              </span>
              <p className="text-xs text-[#0F172A] leading-relaxed whitespace-pre-wrap">
                {task.description || 'No description provided.'}
              </p>
            </div>

            {/* Transcript Evidence if available */}
            {task.evidence && (
              <div className="p-4 rounded-xl bg-[#EFF6FF]/60 border border-[#BFDBFE] space-y-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-[#1E40AF] flex items-center gap-1.5">
                  <CheckSquare className="w-3.5 h-3.5 text-[#2563EB]" />
                  Transcript Evidence & Verbal Quote
                </span>
                <p className="text-xs text-[#1E40AF] italic leading-relaxed">
                  "{task.evidence}"
                </p>
              </div>
            )}

            {/* AI Recommendation Reason & Confidence if present */}
            {task.assignment_reason && (
              <div className="p-3.5 rounded-xl bg-[#F5F3FF] border border-[#DDD6FE] space-y-1 text-xs">
                <span className="text-[10px] font-bold text-[#7C3AED] uppercase tracking-wider">
                  AI Assignment Reason (Confidence: {
                    !task.assigned_member_id || task.assigned_member_name === 'Unassigned'
                      ? '0% – No Match'
                      : `${Math.round((task.confidence_score ?? 0) * 100)}%`
                  })
                </span>
                <p className="text-xs text-[#5B21B6] leading-relaxed">
                  {task.assignment_reason}
                </p>
              </div>
            )}

            {/* Assigned Member Card */}
            <div className="p-4 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-[#2563EB] to-[#7C3AED] flex items-center justify-center text-white font-bold text-xs uppercase shadow-xs">
                  {task.assigned_member_name ? task.assigned_member_name.slice(0, 2) : 'UN'}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-xs font-bold text-[#0F172A]">{task.assigned_member_name || 'Unassigned'}</p>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#EFF6FF] text-[#2563EB] border border-[#BFDBFE]">
                      {task.assigned_member_role || 'Role unassigned'}
                    </span>
                  </div>
                  <p className="text-[11px] text-[#2563EB] font-mono mt-0.5">{task.assigned_member_email || 'No email'}</p>
                </div>
              </div>

              {task.assigned_member_id && (
                <span className="text-[10px] font-mono text-[#64748B] bg-white px-2 py-1 rounded-lg border border-[#E2E8F0]">
                  {task.assigned_member_id}
                </span>
              )}
            </div>

            {/* Required Skills if any */}
            {task.required_skills && task.required_skills.length > 0 && (
              <div className="p-3.5 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0]">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-[#64748B] block mb-2">
                  Required Technical Skills
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {task.required_skills.map((skill, i) => (
                    <span key={i} className="px-2 py-0.5 rounded-md bg-[#EFF6FF] border border-[#BFDBFE] text-xs text-[#1E40AF]">
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Zapier Status Banner */}
            <div className="p-3.5 rounded-xl bg-white border border-[#E2E8F0] flex items-center justify-between text-xs">
              <div className="flex items-center gap-2 text-[#64748B]">
                <Zap className="w-4 h-4 text-[#059669]" />
                <span>Primary source of truth: <strong className="text-[#0F172A]">MongoDB Atlas (tasks)</strong></span>
              </div>
              <span className="text-[10px] text-[#059669] font-semibold bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                Zapier Synchronized
              </span>
            </div>
          </div>
        )}

        {/* Footer Actions */}
        <div className="pt-4 border-t border-[#E2E8F0] flex items-center justify-between">
          <div>
            {isAdmin && !isEditing && (
              <button
                type="button"
                onClick={handleDelete}
                disabled={loading}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-red-50 border border-red-200 text-red-600 hover:bg-red-100 text-xs font-semibold transition cursor-pointer"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>Delete Task</span>
              </button>
            )}
          </div>

          <div className="flex gap-2">
            {!isEditing ? (
              <>
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 rounded-xl text-xs font-semibold text-[#64748B] hover:text-[#0F172A] hover:bg-[#F1F5F9] transition cursor-pointer"
                >
                  Close
                </button>
                {isAdmin && (
                  <button
                    type="button"
                    onClick={() => setIsEditing(true)}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold shadow-xs transition cursor-pointer"
                  >
                    <Edit3 className="w-3.5 h-3.5" />
                    <span>Edit Task</span>
                  </button>
                )}
              </>
            ) : (
              <>
                <button
                  type="button"
                  onClick={() => setIsEditing(false)}
                  className="px-4 py-2 rounded-xl text-xs font-semibold text-[#64748B] hover:text-[#0F172A] hover:bg-[#F1F5F9] transition cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSaveEdits}
                  disabled={loading}
                  className="flex items-center gap-1.5 px-5 py-2 rounded-xl bg-[#059669] hover:bg-[#047857] text-white text-xs font-semibold shadow-xs transition cursor-pointer"
                >
                  <Save className="w-3.5 h-3.5" />
                  <span>{loading ? 'Saving...' : 'Save Changes'}</span>
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
}
