import React, { useState } from 'react';
import Modal from '../components/Modal';
import api from '../services/api';
import { 
  UploadCloud, 
  Download, 
  CheckCircle2, 
  AlertTriangle, 
  XCircle,
  FileCheck
} from 'lucide-react';

export default function BulkImportModal({ isOpen, onClose, onImportCompleted }) {
  const [file, setFile] = useState(null);
  const [previewData, setPreviewData] = useState(null);
  const [activeTab, setActiveTab] = useState('valid');
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const handleDownloadTemplate = async () => {
    try {
      const res = await api.get('/team/members/template', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'meetmind_team_template.csv');
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      setError('Failed to download CSV template.');
    }
  };

  const handleFileChange = (e) => {
    const selected = e.target.files[0];
    if (selected) {
      setFile(selected);
      setError('');
      setSuccess('');
      setPreviewData(null);
      runPreview(selected);
    }
  };

  const runPreview = async (selectedFile) => {
    setLoading(true);
    setError('');
    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const res = await api.post('/team/members/import?preview=true', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setPreviewData(res.data);
      if (res.data.valid_count === 0 && res.data.invalid_count > 0) {
        setActiveTab('invalid');
      } else {
        setActiveTab('valid');
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to preview file.');
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmImport = async () => {
    if (!file) return;
    setImporting(true);
    setError('');
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await api.post('/team/members/import?preview=false', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setSuccess(`Successfully imported ${res.data.imported_count} members into MongoDB Atlas!`);
      setTimeout(() => {
        onImportCompleted();
        onClose();
        setFile(null);
        setPreviewData(null);
        setSuccess('');
      }, 1000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Import failed.');
    } finally {
      setImporting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Bulk Import Team Members"
      subtitle="Upload CSV or Excel file to persist members into MongoDB member_profiles"
      maxWidth="max-w-4xl"
    >
      {/* Action Header */}
      <div className="flex items-center justify-between pb-4 border-b border-[#E2E8F0] mb-4">
        <div>
          <p className="text-xs text-[#64748B]">
            Upload a CSV or Excel (.xlsx) file containing member profiles.
          </p>
        </div>
        <button
          onClick={handleDownloadTemplate}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#EFF6FF] border border-[#BFDBFE] text-[#2563EB] hover:bg-[#DBEAFE] text-xs font-semibold transition cursor-pointer"
        >
          <Download className="w-3.5 h-3.5" />
          <span>Download Sample CSV</span>
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
          <XCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="mb-4 p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
          <span>{success}</span>
        </div>
      )}

      {/* File Dropzone */}
      <div className="border-2 border-dashed border-[#CBD5E1] hover:border-[#2563EB] rounded-2xl p-6 text-center bg-[#F8FAFC] transition cursor-pointer relative">
        <input
          type="file"
          accept=".csv, .xlsx, .xls"
          onChange={handleFileChange}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
        />
        <div className="flex flex-col items-center justify-center gap-2">
          <div className="w-12 h-12 rounded-xl bg-[#EFF6FF] border border-[#BFDBFE] flex items-center justify-center text-[#2563EB]">
            <UploadCloud className="w-6 h-6" />
          </div>
          <div>
            <p className="text-sm font-semibold text-[#0F172A]">
              {file ? file.name : 'Click or drag & drop CSV or Excel file'}
            </p>
            <p className="text-xs text-[#64748B] mt-0.5">
              Supports .csv and .xlsx (columns: name, email, role, skills, experience, availability, maximum_workload)
            </p>
          </div>
        </div>
      </div>

      {loading && (
        <div className="py-8 text-center text-xs text-[#64748B] flex items-center justify-center gap-2">
          <div className="w-4 h-4 border-2 border-[#2563EB] border-t-transparent rounded-full animate-spin" />
          <span>Validating spreadsheet rows and detecting duplicates...</span>
        </div>
      )}

      {/* Preview Summary */}
      {previewData && !loading && (
        <div className="mt-6 space-y-4">
          <div className="grid grid-cols-4 gap-3">
            <div className="p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0]">
              <span className="text-[10px] text-[#64748B] uppercase font-semibold">Total Rows</span>
              <p className="text-lg font-bold text-[#0F172A]">{previewData.total_rows}</p>
            </div>
            <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200">
              <span className="text-[10px] text-emerald-700 uppercase font-semibold">Valid Members</span>
              <p className="text-lg font-bold text-emerald-700">{previewData.valid_count}</p>
            </div>
            <div className="p-3 rounded-xl bg-red-50 border border-red-200">
              <span className="text-[10px] text-red-700 uppercase font-semibold">Invalid Rows</span>
              <p className="text-lg font-bold text-red-700">{previewData.invalid_count}</p>
            </div>
            <div className="p-3 rounded-xl bg-amber-50 border border-amber-200">
              <span className="text-[10px] text-amber-700 uppercase font-semibold">Duplicate Emails</span>
              <p className="text-lg font-bold text-amber-700">{previewData.duplicate_emails.length}</p>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex border-b border-[#E2E8F0] gap-4">
            <button
              onClick={() => setActiveTab('valid')}
              className={`pb-2.5 text-xs font-semibold flex items-center gap-1.5 transition border-b-2 -mb-px cursor-pointer ${
                activeTab === 'valid'
                  ? 'border-[#059669] text-[#059669]'
                  : 'border-transparent text-[#64748B] hover:text-[#0F172A]'
              }`}
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Valid Records ({previewData.valid_count})</span>
            </button>
            <button
              onClick={() => setActiveTab('invalid')}
              className={`pb-2.5 text-xs font-semibold flex items-center gap-1.5 transition border-b-2 -mb-px cursor-pointer ${
                activeTab === 'invalid'
                  ? 'border-red-600 text-red-600'
                  : 'border-transparent text-[#64748B] hover:text-[#0F172A]'
              }`}
            >
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>Invalid Records ({previewData.invalid_count})</span>
            </button>
          </div>

          {/* Table Container */}
          <div className="max-h-60 overflow-y-auto rounded-xl border border-[#E2E8F0] bg-white">
            {activeTab === 'valid' ? (
              previewData.valid_rows.length === 0 ? (
                <div className="p-6 text-center text-xs text-[#64748B]">No valid rows found in file.</div>
              ) : (
                <table className="w-full text-left text-xs">
                  <thead className="bg-[#F8FAFC] text-[#64748B] sticky top-0 border-b border-[#E2E8F0]">
                    <tr>
                      <th className="p-2.5">Row</th>
                      <th className="p-2.5">Name</th>
                      <th className="p-2.5">Email</th>
                      <th className="p-2.5">Role</th>
                      <th className="p-2.5">Skills</th>
                      <th className="p-2.5">Workload</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#E2E8F0]">
                    {previewData.valid_rows.map((row) => (
                      <tr key={row.row_number} className="hover:bg-[#F8FAFC]">
                        <td className="p-2.5 text-[#64748B]">#{row.row_number}</td>
                        <td className="p-2.5 font-semibold text-[#0F172A]">{row.name}</td>
                        <td className="p-2.5 text-[#2563EB]">{row.email}</td>
                        <td className="p-2.5 text-[#0F172A]">{row.role}</td>
                        <td className="p-2.5 text-[#64748B]">{row.skills.join(', ')}</td>
                        <td className="p-2.5 text-[#0F172A]">{row.maximum_workload} tasks</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
            ) : (
              previewData.invalid_rows.length === 0 ? (
                <div className="p-6 text-center text-xs text-[#059669]">All rows in this file are valid!</div>
              ) : (
                <table className="w-full text-left text-xs">
                  <thead className="bg-[#F8FAFC] text-[#64748B] sticky top-0 border-b border-[#E2E8F0]">
                    <tr>
                      <th className="p-2.5">Row</th>
                      <th className="p-2.5">Name</th>
                      <th className="p-2.5">Email</th>
                      <th className="p-2.5 text-red-600">Error / Rejection Reason</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#E2E8F0]">
                    {previewData.invalid_rows.map((row) => (
                      <tr key={row.row_number} className="hover:bg-red-50/50">
                        <td className="p-2.5 text-[#64748B]">#{row.row_number}</td>
                        <td className="p-2.5 font-semibold text-[#0F172A]">{row.name || '—'}</td>
                        <td className="p-2.5 text-[#64748B]">{row.email || '—'}</td>
                        <td className="p-2.5 text-red-600 font-medium">{row.error}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
            )}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="mt-6 pt-4 border-t border-[#E2E8F0] flex items-center justify-between">
        <p className="text-[11px] text-[#64748B]">
          Inserted with <span className="font-mono text-[#0F172A]">registration_method: "csv_import"</span>
        </p>
        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-[#64748B] hover:text-[#0F172A] hover:bg-[#F1F5F9] transition cursor-pointer"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirmImport}
            disabled={!previewData || previewData.valid_count === 0 || importing}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#059669] hover:bg-[#047857] text-white text-xs font-semibold shadow-sm transition disabled:opacity-40 cursor-pointer"
          >
            <FileCheck className="w-4 h-4" />
            <span>{importing ? 'Importing into MongoDB...' : `Import ${previewData?.valid_count || 0} Members`}</span>
          </button>
        </div>
      </div>
    </Modal>
  );
}
