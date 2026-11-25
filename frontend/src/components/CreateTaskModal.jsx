import React, { useState } from 'react';
import Modal from './Modal';
import api from '../services/api';
import { PlusCircle, AlertCircle, CheckCircle2 } from 'lucide-react';

export default function CreateTaskModal({ isOpen, onClose, onTaskCreated, teamMembers = [] }) {
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    priority: 'Medium',
    deadline: '',
    meeting_title: 'Sprint Planning',
    assigned_member_id: '',
    required_skills: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
    setError('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const skillsArray = formData.required_skills
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);

      const payload = {
        title: formData.title.trim(),
        description: formData.description.trim(),
        priority: formData.priority,
        deadline: formData.deadline.trim() || null,
        meeting_title: formData.meeting_title.trim() || 'Manual Task',
        assigned_member_id: formData.assigned_member_id || null,
        required_skills: skillsArray,
      };

      const res = await api.post('/tasks', payload);
      setSuccess(`Task "${res.data.title}" created and saved to MongoDB!`);
      setTimeout(() => {
        onTaskCreated();
        onClose();
        setFormData({
          title: '',
          description: '',
          priority: 'Medium',
          deadline: '',
          meeting_title: 'Sprint Planning',
          assigned_member_id: '',
          required_skills: '',
        });
        setSuccess('');
      }, 900);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create task.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Create New Task"
      subtitle="Creates task in MongoDB Atlas tasks collection and triggers Zapier automation"
      maxWidth="max-w-2xl"
    >
      {error && (
        <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="mb-4 p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
          <span>{success}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-semibold text-[#475569] mb-1.5">
            Task Title *
          </label>
          <input
            type="text"
            name="title"
            required
            value={formData.title}
            onChange={handleChange}
            placeholder="e.g. Develop login page using React"
            className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:outline-none focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB] transition"
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-[#475569] mb-1.5">
            Task Description
          </label>
          <textarea
            name="description"
            rows={3}
            value={formData.description}
            onChange={handleChange}
            placeholder="Detailed requirements, deliverables, or context..."
            className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:outline-none focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB] transition"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-[#475569] mb-1.5">
              Priority
            </label>
            <select
              name="priority"
              value={formData.priority}
              onChange={handleChange}
              className="w-full px-3 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:border-[#2563EB]"
            >
              <option value="Low">Low</option>
              <option value="Medium">Medium</option>
              <option value="High">High</option>
              <option value="Critical">Critical</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#475569] mb-1.5">
              Deadline
            </label>
            <input
              type="date"
              name="deadline"
              value={formData.deadline}
              onChange={handleChange}
              className="w-full px-3 py-2 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-[#475569] mb-1.5">
              Meeting Title
            </label>
            <input
              type="text"
              name="meeting_title"
              value={formData.meeting_title}
              onChange={handleChange}
              placeholder="e.g. Sprint Planning #1"
              className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#475569] mb-1.5">
              Assign Team Member
            </label>
            <select
              name="assigned_member_id"
              value={formData.assigned_member_id}
              onChange={handleChange}
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

        <div>
          <label className="block text-xs font-semibold text-[#475569] mb-1.5">
            Required Technical Skills (comma-separated)
          </label>
          <input
            type="text"
            name="required_skills"
            value={formData.required_skills}
            onChange={handleChange}
            placeholder="e.g. React, JavaScript, Node.js"
            className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs"
          />
        </div>

        <div className="pt-4 border-t border-[#E2E8F0] flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-[#64748B] hover:text-[#0F172A] hover:bg-[#F1F5F9] transition cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={loading}
            className="flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold shadow-xs transition disabled:opacity-50 cursor-pointer"
          >
            <PlusCircle className="w-4 h-4" />
            <span>{loading ? 'Creating Task...' : 'Create Task'}</span>
          </button>
        </div>
      </form>
    </Modal>
  );
}
