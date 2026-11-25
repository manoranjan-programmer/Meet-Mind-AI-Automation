import React, { useState } from 'react';
import Modal from '../components/Modal';
import api from '../services/api';
import { UserPlus, AlertCircle, CheckCircle2 } from 'lucide-react';

export default function AddMemberModal({ isOpen, onClose, onMemberAdded }) {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    role: '',
    skills: '',
    experience: 'Intermediate',
    availability: 'Available',
    maximum_workload: 5,
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
    setSuccess('');

    try {
      const skillsArray = formData.skills
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);

      const payload = {
        name: formData.name.trim(),
        email: formData.email.trim(),
        role: formData.role.trim(),
        skills: skillsArray,
        experience: formData.experience,
        availability: formData.availability,
        maximum_workload: parseInt(formData.maximum_workload) || 5,
      };

      const res = await api.post('/team/members', payload);
      setSuccess(`Member ${res.data.name} successfully registered to MongoDB!`);
      setTimeout(() => {
        onMemberAdded();
        onClose();
        setFormData({
          name: '',
          email: '',
          role: '',
          skills: '',
          experience: 'Intermediate',
          availability: 'Available',
          maximum_workload: 5,
        });
        setSuccess('');
      }, 900);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to add member. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Add Team Member"
      subtitle="Manual registration into MongoDB Atlas member_profiles collection"
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
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-[#475569] mb-1.5">
              Full Name *
            </label>
            <input
              type="text"
              name="name"
              required
              value={formData.name}
              onChange={handleChange}
              placeholder="e.g. Jai"
              className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:outline-none focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB] transition"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#475569] mb-1.5">
              Email Address *
            </label>
            <input
              type="email"
              name="email"
              required
              value={formData.email}
              onChange={handleChange}
              placeholder="e.g. jai@example.com"
              className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:outline-none focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB] transition"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-semibold text-[#475569] mb-1.5">
            Job Role *
          </label>
          <input
            type="text"
            name="role"
            required
            value={formData.role}
            onChange={handleChange}
            placeholder="e.g. Frontend Developer"
            className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:outline-none focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB] transition"
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-[#475569] mb-1.5">
            Technical Skills (comma-separated)
          </label>
          <input
            type="text"
            name="skills"
            value={formData.skills}
            onChange={handleChange}
            placeholder="e.g. React, JavaScript, HTML, CSS"
            className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:outline-none focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB] transition"
          />
          <p className="text-[11px] text-[#64748B] mt-1">
            Skills are indexed for autonomous multi-agent task matching.
          </p>
        </div>

        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="block text-xs font-semibold text-[#475569] mb-1.5">
              Experience Level
            </label>
            <select
              name="experience"
              value={formData.experience}
              onChange={handleChange}
              className="w-full px-3 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:outline-none focus:border-[#2563EB]"
            >
              <option value="Junior">Junior</option>
              <option value="Intermediate">Intermediate</option>
              <option value="Senior">Senior</option>
              <option value="Advanced">Advanced</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#475569] mb-1.5">
              Availability Status
            </label>
            <select
              name="availability"
              value={formData.availability}
              onChange={handleChange}
              className="w-full px-3 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:outline-none focus:border-[#2563EB]"
            >
              <option value="Available">Available</option>
              <option value="Busy">Busy</option>
              <option value="On Leave">On Leave</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#475569] mb-1.5">
              Max Workload (tasks)
            </label>
            <input
              type="number"
              name="maximum_workload"
              min="1"
              max="20"
              value={formData.maximum_workload}
              onChange={handleChange}
              className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#CBD5E1] text-[#0F172A] text-xs focus:outline-none focus:border-[#2563EB]"
            />
          </div>
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
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold shadow-sm transition disabled:opacity-50 cursor-pointer"
          >
            <UserPlus className="w-4 h-4" />
            <span>{loading ? 'Saving...' : 'Add Member'}</span>
          </button>
        </div>
      </form>
    </Modal>
  );
}
