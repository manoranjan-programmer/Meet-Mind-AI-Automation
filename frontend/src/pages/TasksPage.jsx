import React, { useState, useEffect } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  TouchSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  useDroppable,
  closestCorners,
} from '@dnd-kit/core';
import {
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
  sortableKeyboardCoordinates,
  arrayMove,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { 
  CheckSquare, 
  Plus, 
  Search, 
  Filter, 
  Calendar, 
  User, 
  Clock, 
  CheckCircle2, 
  ChevronRight, 
  ChevronLeft, 
  Tag, 
  Kanban, 
  Table as TableIcon,
  Layers
} from 'lucide-react';
import TaskDetailsModal from '../components/TaskDetailsModal';
import CreateTaskModal from '../components/CreateTaskModal';

const COLUMNS = [
  { id: 'To Do', label: 'To Do', headerBg: '#FEF3C7', countBg: '#F59E0B', textColor: '#92400E', borderColor: '#FDE68A' },
  { id: 'In Progress', label: 'In Progress', headerBg: '#EFF6FF', countBg: '#2563EB', textColor: '#1E40AF', borderColor: '#BFDBFE' },
  { id: 'Review', label: 'Review', headerBg: '#F5F3FF', countBg: '#7C3AED', textColor: '#5B21B6', borderColor: '#DDD6FE' },
  { id: 'Completed', label: 'Completed', headerBg: '#ECFDF5', countBg: '#059669', textColor: '#065F46', borderColor: '#A7F3D0' },
];

function DroppableKanbanColumn({ col, isOver, children }) {
  const { setNodeRef } = useDroppable({ id: col.id, data: { type: 'column', columnId: col.id } });
  return (
    <div
      ref={setNodeRef}
      className={`rounded-2xl bg-[#F8FAFC] border flex flex-col min-h-[580px] shadow-sm transition-all ${
        isOver ? 'border-[#2563EB] ring-2 ring-[#2563EB]/30 bg-[#EFF6FF]/40' : 'border-[#E2E8F0]'
      }`}
    >
      {children}
    </div>
  );
}

function SortableTaskCard({ task, isMoving, children, onClick }) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: task.task_id, data: { type: 'task', task } });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={onClick}
      className={`p-4 rounded-xl bg-white border transition-all cursor-grab active:cursor-grabbing group space-y-3 relative touch-none ${
        isDragging
          ? 'border-[#2563EB] shadow-lg'
          : isMoving
          ? 'border-[#2563EB]/60 opacity-80 pointer-events-none'
          : 'border-[#E2E8F0] hover:border-[#2563EB]/50 hover:shadow-md'
      }`}
    >
      {children}
    </div>
  );
}

export default function TasksPage() {
  const { user } = useAuth();
  const { taskId: routeTaskId } = useParams();
  const [searchParams] = useSearchParams();
  const deepLinkTaskId = routeTaskId || searchParams.get('task_id');
  const isLeader = ['admin', 'team lead', 'team leader', 'team_leader', 'manager', 'team lead / admin', 'team leader / admin'].includes(
    (user?.role || '').toLowerCase()
  );

  const [tasks, setTasks] = useState([]);
  const [counts, setCounts] = useState({ todo: 0, in_progress: 0, review: 0, completed: 0, total: 0 });
  const [meetings, setMeetings] = useState([]);
  const [teamMembers, setTeamMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [displayMode, setDisplayMode] = useState('kanban'); // 'kanban' | 'table'
  const [deepLinkError, setDeepLinkError] = useState('');
  const [activeDragTask, setActiveDragTask] = useState(null);
  const [overColumnId, setOverColumnId] = useState(null);
  const [movingTaskId, setMovingTaskId] = useState(null);
  const [dndFeedback, setDndFeedback] = useState({ type: '', message: '' });

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 180, tolerance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  // Filters
  const [search, setSearch] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('All');
  const [memberFilter, setMemberFilter] = useState('All');
  const [meetingFilter, setMeetingFilter] = useState('All');
  const [approvalFilter, setApprovalFilter] = useState('All'); // 'All' | 'Approved' | 'Awaiting Approval' | 'Rejected'
  const [viewMode, setViewMode] = useState(isLeader ? 'all' : 'my'); // 'all' | 'my'

  // Modals
  const [selectedTask, setSelectedTask] = useState(null);
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  // Open exact task when navigated via email deep link (/tasks/:taskId or /tasks?task_id=...)
  useEffect(() => {
    if (!deepLinkTaskId) return;
    setDeepLinkError('');
    api.get(`/tasks/${encodeURIComponent(deepLinkTaskId)}`)
      .then((res) => {
        setSelectedTask(res.data);
        setIsDetailsOpen(true);
      })
      .catch((err) => {
        setDeepLinkError(err.response?.data?.detail || 'You do not have permission to view this task or it does not exist.');
      });
  }, [deepLinkTaskId]);

  const fetchTasks = async () => {
    setLoading(true);
    try {
      const params = {};
      if (search) params.search = search;
      if (priorityFilter !== 'All') params.priority = priorityFilter;
      if (memberFilter !== 'All') params.assigned_member_id = memberFilter;
      if (meetingFilter !== 'All') params.meeting_id = meetingFilter;
      if (approvalFilter !== 'All') params.approval_status = approvalFilter;
      if (viewMode === 'my') params.view_mode = 'my';

      const res = await api.get('/tasks', { params });
      setTasks(res.data.tasks || []);
      setCounts(res.data.counts || { todo: 0, in_progress: 0, review: 0, completed: 0, total: 0 });
      setMeetings(res.data.meetings || []);
    } catch (err) {
      console.error('Failed to fetch tasks', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchTeamMembers = async () => {
    try {
      const res = await api.get('/team/members?status=active');
      setTeamMembers(res.data.members || []);
    } catch (err) {
      console.error('Failed to fetch team members', err);
    }
  };

  useEffect(() => {
    fetchTeamMembers();
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchTasks();
    }, 200);
    return () => clearTimeout(timer);
  }, [search, priorityFilter, memberFilter, meetingFilter, approvalFilter, viewMode]);

  const [approvingTaskId, setApprovingTaskId] = useState(null);

  const handleApproveTask = async (e, task) => {
    e.stopPropagation();
    setApprovingTaskId(task.task_id);
    try {
      await api.post(`/tasks/${task.task_id}/approve`);
      await fetchTasks();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to approve task.');
    } finally {
      setApprovingTaskId(null);
    }
  };

  const handleRejectTask = async (e, task) => {
    e.stopPropagation();
    if (!window.confirm('Are you sure you want to reject this task?')) return;
    try {
      await api.post(`/tasks/${task.task_id}/reject`);
      fetchTasks();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to reject task.');
    }
  };

  const handleQuickStatusMove = async (e, task, newStatus) => {
    e.stopPropagation();
    try {
      await api.patch(`/tasks/${task.task_id}/status`, { status: newStatus, trigger_automation: true });
      fetchTasks();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to move task status.');
    }
  };

  const showFeedback = (type, message) => {
    setDndFeedback({ type, message });
    setTimeout(() => {
      setDndFeedback((prev) => (prev.message === message ? { type: '', message: '' } : prev));
    }, 3200);
  };

  const handleDragStart = (event) => {
    const dragged = tasks.find((t) => t.task_id === event.active.id);
    setActiveDragTask(dragged || null);
    setDndFeedback({ type: '', message: '' });
  };

  const handleDragOver = (event) => {
    const { over } = event;
    if (!over) {
      setOverColumnId(null);
      return;
    }
    const overCol = COLUMNS.find((c) => c.id === over.id)?.id
      || tasks.find((t) => t.task_id === over.id)?.status
      || null;
    setOverColumnId(overCol);
  };

  const handleDragEnd = async (event) => {
    const { active, over } = event;
    setActiveDragTask(null);
    setOverColumnId(null);
    if (!over) return;

    const draggedTask = tasks.find((t) => t.task_id === active.id);
    if (!draggedTask || movingTaskId === draggedTask.task_id) return;

    const targetColumn = COLUMNS.find((c) => c.id === over.id)?.id
      || tasks.find((t) => t.task_id === over.id)?.status;
    if (!targetColumn) return;

    const sourceColumn = draggedTask.status;

    // Preserve approval workflow: unapproved tasks cannot leave 'To Do'
    if (targetColumn !== 'To Do' && draggedTask.approval_status !== 'Approved') {
      showFeedback('error', `Task ${draggedTask.task_id} must be approved by the Team Leader before moving to ${targetColumn}.`);
      return;
    }

    // Reordering within the same column
    if (sourceColumn === targetColumn) {
      if (active.id === over.id) return;
      const colTasks = tasks.filter((t) => t.status === sourceColumn);
      const oldIdx = colTasks.findIndex((t) => t.task_id === active.id);
      const newIdx = colTasks.findIndex((t) => t.task_id === over.id);
      if (oldIdx === -1 || newIdx === -1 || oldIdx === newIdx) return;

      const reorderedCol = arrayMove(colTasks, oldIdx, newIdx);
      const previousTasks = [...tasks];
      const otherTasks = tasks.filter((t) => t.status !== sourceColumn);
      const updatedReordered = reorderedCol.map((t, idx) => ({ ...t, order: idx }));
      setTasks([...otherTasks, ...updatedReordered]);

      setMovingTaskId(draggedTask.task_id);
      try {
        await api.patch(`/tasks/${draggedTask.task_id}/status`, {
          status: targetColumn,
          order: newIdx,
          trigger_automation: false,
        });
        showFeedback('success', `Reordered ${draggedTask.task_id} in ${targetColumn}.`);
      } catch (err) {
        setTasks(previousTasks);
        showFeedback('error', err.response?.data?.detail || 'Failed to save task order.');
      } finally {
        setMovingTaskId(null);
      }
      return;
    }

    // Moving across columns (optimistic update + rollback on failure; never triggers Zapier)
    const previousTasks = [...tasks];
    const destColTasks = tasks.filter((t) => t.status === targetColumn);
    const overTaskIdx = destColTasks.findIndex((t) => t.task_id === over.id);
    const newOrder = overTaskIdx >= 0 ? overTaskIdx : destColTasks.length;

    setTasks((prev) =>
      prev.map((t) =>
        t.task_id === draggedTask.task_id ? { ...t, status: targetColumn, order: newOrder } : t
      )
    );
    setMovingTaskId(draggedTask.task_id);

    try {
      const res = await api.patch(`/tasks/${draggedTask.task_id}/status`, {
        status: targetColumn,
        order: newOrder,
        trigger_automation: false,
      });
      const updatedFromServer = res.data;
      setTasks((prev) =>
        prev.map((t) => (t.task_id === draggedTask.task_id ? { ...t, ...updatedFromServer } : t))
      );
      showFeedback('success', `Moved ${draggedTask.task_id} to ${targetColumn}.`);
    } catch (err) {
      setTasks(previousTasks);
      showFeedback('error', err.response?.data?.detail || `Could not move ${draggedTask.task_id} to ${targetColumn}.`);
    } finally {
      setMovingTaskId(null);
    }
  };

  const openTaskDetails = (task) => {
    setSelectedTask(task);
    setIsDetailsOpen(true);
  };

  const getPriorityBadgeClass = (priority) => {
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

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold text-[#0F172A] tracking-tight flex items-center gap-2.5">
              <CheckSquare className="w-5 h-5 text-[#2563EB]" />
              <span>Task Management</span>
            </h2>
            <span className="text-[10px] px-2.5 py-0.5 rounded-full font-bold bg-[#EFF6FF] text-[#2563EB] border border-[#BFDBFE]">
              MongoDB Atlas Tasks
            </span>
          </div>
          <p className="text-xs text-[#64748B] mt-1">
            Kanban workflow, AI assignment tracking, Zapier automation dispatch, and live status transitions.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          {/* View Toggle: Kanban vs Table */}
          <div className="flex items-center p-1 rounded-xl bg-white border border-[#E2E8F0] shadow-sm text-xs">
            <button
              onClick={() => setDisplayMode('kanban')}
              className={`p-1.5 rounded-lg transition cursor-pointer flex items-center gap-1 ${
                displayMode === 'kanban'
                  ? 'bg-[#EFF6FF] text-[#2563EB] font-semibold'
                  : 'text-[#64748B] hover:text-[#0F172A]'
              }`}
              title="Kanban Board View"
            >
              <Kanban className="w-3.5 h-3.5" />
              <span className="text-[11px] font-medium hidden sm:inline">Kanban</span>
            </button>
            <button
              onClick={() => setDisplayMode('table')}
              className={`p-1.5 rounded-lg transition cursor-pointer flex items-center gap-1 ${
                displayMode === 'table'
                  ? 'bg-[#EFF6FF] text-[#2563EB] font-semibold'
                  : 'text-[#64748B] hover:text-[#0F172A]'
              }`}
              title="Table View"
            >
              <TableIcon className="w-3.5 h-3.5" />
              <span className="text-[11px] font-medium hidden sm:inline">Table</span>
            </button>
          </div>

          {/* All vs My Tasks (Team Leaders only; Members see only their assigned tasks) */}
          {isLeader && (
            <div className="flex items-center p-1 rounded-xl bg-white border border-[#E2E8F0] shadow-sm text-xs">
              <button
                onClick={() => setViewMode('all')}
                className={`px-3 py-1.5 rounded-lg font-semibold transition cursor-pointer ${
                  viewMode === 'all'
                    ? 'bg-[#2563EB] text-white shadow-sm'
                    : 'text-[#64748B] hover:text-[#0F172A]'
                }`}
              >
                All Tasks
              </button>
              <button
                onClick={() => setViewMode('my')}
                className={`px-3 py-1.5 rounded-lg font-semibold transition cursor-pointer ${
                  viewMode === 'my'
                    ? 'bg-[#2563EB] text-white shadow-sm'
                    : 'text-[#64748B] hover:text-[#0F172A]'
                }`}
              >
                My Tasks
              </button>
            </div>
          )}

          <button
            onClick={() => setIsCreateOpen(true)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold shadow-sm transition cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            <span>New Task</span>
          </button>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="p-4 rounded-2xl bg-white border border-[#E2E8F0] shadow-sm flex flex-wrap items-center justify-between gap-4">
        {/* Search */}
        <div className="relative w-full sm:w-72">
          <Search className="w-4 h-4 text-[#94A3B8] absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search tasks, task ID, title..."
            className="w-full pl-9 pr-3.5 py-2 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-xs text-[#0F172A] placeholder-[#94A3B8] focus:outline-none focus:border-[#2563EB] focus:bg-white transition"
          />
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3 text-xs">
          {/* Priority */}
          <div className="flex items-center gap-1.5 bg-[#F8FAFC] px-3 py-1.5 rounded-xl border border-[#E2E8F0]">
            <span className="text-[#64748B]">Priority:</span>
            <select
              value={priorityFilter}
              onChange={(e) => setPriorityFilter(e.target.value)}
              className="bg-transparent text-[#0F172A] font-medium focus:outline-none cursor-pointer"
            >
              <option value="All">All Priorities</option>
              <option value="Critical">Critical</option>
              <option value="High">High</option>
              <option value="Medium">Medium</option>
              <option value="Low">Low</option>
            </select>
          </div>

          {/* Approval Filter */}
          <div className="flex items-center gap-1.5 bg-[#F8FAFC] px-3 py-1.5 rounded-xl border border-[#E2E8F0]">
            <span className="text-[#64748B]">Approval:</span>
            <select
              value={approvalFilter}
              onChange={(e) => setApprovalFilter(e.target.value)}
              className="bg-transparent text-[#0F172A] font-medium focus:outline-none cursor-pointer"
            >
              <option value="All">All Statuses</option>
              <option value="Approved">Approved</option>
              <option value="Awaiting Approval">Awaiting Approval</option>
              <option value="Rejected">Rejected</option>
            </select>
          </div>

          {/* Member (Team Leaders only) */}
          {isLeader && (
            <div className="flex items-center gap-1.5 bg-[#F8FAFC] px-3 py-1.5 rounded-xl border border-[#E2E8F0]">
              <User className="w-3.5 h-3.5 text-[#2563EB]" />
              <select
                value={memberFilter}
                onChange={(e) => setMemberFilter(e.target.value)}
                className="bg-transparent text-[#0F172A] font-medium focus:outline-none cursor-pointer"
              >
                <option value="All">All Members</option>
                {teamMembers.map((m) => (
                  <option key={m.member_id} value={m.member_id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Meeting */}
          {meetings.length > 0 && (
            <div className="flex items-center gap-1.5 bg-[#F8FAFC] px-3 py-1.5 rounded-xl border border-[#E2E8F0]">
              <Tag className="w-3.5 h-3.5 text-[#7C3AED]" />
              <select
                value={meetingFilter}
                onChange={(e) => setMeetingFilter(e.target.value)}
                className="bg-transparent text-[#0F172A] font-medium focus:outline-none cursor-pointer max-w-xs truncate"
              >
                <option value="All">All Meetings</option>
                {meetings.map((mtg, i) => (
                  <option key={i} value={mtg}>
                    {mtg}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </div>

      {deepLinkError && (
        <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs font-medium flex items-center justify-between">
          <span>{deepLinkError}</span>
          <button onClick={() => setDeepLinkError('')} className="text-rose-500 hover:text-rose-700 font-bold cursor-pointer">✕</button>
        </div>
      )}

      {dndFeedback.message && (
        <div
          className={`p-3 rounded-xl border text-xs font-medium flex items-center justify-between ${
            dndFeedback.type === 'error'
              ? 'bg-rose-50 border-rose-200 text-rose-700'
              : 'bg-emerald-50 border-emerald-200 text-emerald-700'
          }`}
        >
          <span>{dndFeedback.message}</span>
          <button
            onClick={() => setDndFeedback({ type: '', message: '' })}
            className="font-bold cursor-pointer ml-2"
          >
            ✕
          </button>
        </div>
      )}

      {/* Main Display: Kanban View or Table View */}
      {displayMode === 'kanban' ? (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCorners}
          onDragStart={handleDragStart}
          onDragOver={handleDragOver}
          onDragEnd={handleDragEnd}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {COLUMNS.map((col) => {
              const colTasks = tasks.filter((t) => t.status === col.id);
              const colCount = colTasks.length;
              const isOver = overColumnId === col.id && activeDragTask?.status !== col.id;

              return (
                <DroppableKanbanColumn key={col.id} col={col} isOver={isOver}>
                  {/* Column Header */}
                  <div 
                    className="px-4 py-3 border-b flex items-center justify-between rounded-t-2xl"
                    style={{ backgroundColor: col.headerBg, borderColor: col.borderColor }}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className="w-2.5 h-2.5 rounded-full"
                        style={{ backgroundColor: col.countBg }}
                      />
                      <h3 className="text-xs font-bold tracking-wide uppercase" style={{ color: col.textColor }}>
                        {col.label}
                      </h3>
                    </div>
                    <span 
                      className="text-xs px-2 py-0.5 rounded-full font-bold bg-white shadow-xs"
                      style={{ color: col.textColor }}
                    >
                      {colCount}
                    </span>
                  </div>

                  {/* Column Task Cards */}
                  <SortableContext items={colTasks.map((t) => t.task_id)} strategy={verticalListSortingStrategy}>
                    <div className="p-3 flex-1 space-y-3 overflow-y-auto">
                      {loading ? (
                        <div className="py-12 text-center text-xs text-[#64748B] flex flex-col items-center justify-center gap-2">
                          <div className="w-4 h-4 border-2 border-[#2563EB] border-t-transparent rounded-full animate-spin" />
                          <span>Syncing tasks...</span>
                        </div>
                      ) : colCount === 0 ? (
                        <div className={`py-12 text-center text-xs border border-dashed rounded-xl transition ${
                          isOver
                            ? 'text-[#2563EB] border-[#2563EB] bg-[#EFF6FF]/60 font-semibold'
                            : 'text-[#94A3B8] border-[#CBD5E1] bg-white/50'
                        }`}>
                          {isOver ? `Drop here to move to ${col.label}` : `No tasks in ${col.label}`}
                        </div>
                      ) : (
                        <>
                          {colTasks.map((task) => (
                            <SortableTaskCard
                              key={task.task_id}
                              task={task}
                              isMoving={movingTaskId === task.task_id}
                              onClick={() => openTaskDetails(task)}
                            >
                        {/* Header: Task ID & Priority */}
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-mono font-semibold text-[#64748B] group-hover:text-[#2563EB] transition">
                            {task.task_id}
                          </span>
                          <div className="flex items-center gap-1.5">
                            {isLeader && task.approval_status === 'Awaiting Approval' && (
                              <span className="px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                                AI Queued
                              </span>
                            )}
                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${getPriorityBadgeClass(task.priority)}`}>
                              {task.priority}
                            </span>
                          </div>
                        </div>

                        {/* Title & Meeting */}
                        <div>
                          <h4 className="text-xs font-bold text-[#0F172A] line-clamp-2 group-hover:text-[#2563EB] transition leading-snug">
                            {task.title}
                          </h4>
                          {task.meeting_title && (
                            <p className="text-[10px] text-[#64748B] mt-1 flex items-center gap-1 truncate">
                              <Tag className="w-3 h-3 text-[#7C3AED] flex-shrink-0" />
                              <span className="truncate">{task.meeting_title}</span>
                            </p>
                          )}
                        </div>

                        {/* Description Preview */}
                        {task.description && (
                          <p className="text-[11px] text-[#64748B] line-clamp-2 leading-relaxed">
                            {task.description}
                          </p>
                        )}

                        {/* Deadline */}
                        {task.deadline && (
                          <div className="flex items-center gap-1.5 text-[10px] text-[#64748B]">
                            <Calendar className="w-3 h-3 text-[#2563EB]" />
                            <span>Due: {task.deadline}</span>
                          </div>
                        )}

                        {/* AI Approval Actions Banner for Unapproved Tasks */}
                        {task.approval_status === 'Awaiting Approval' && isLeader && (
                          <div className="p-2.5 rounded-lg bg-amber-50/70 border border-amber-200/80 space-y-2">
                            <p className="text-[10px] font-medium text-amber-800 leading-tight">
                              AI recommended this task from meeting transcript.
                            </p>
                            {task.evidence && (
                              <p className="text-[10px] text-[#2563EB] italic line-clamp-1 bg-white/70 p-1 rounded border border-[#BFDBFE]/60">
                                "{task.evidence}"
                              </p>
                            )}
                            <div className="flex items-center gap-1.5">
                              <button
                                type="button"
                                disabled={approvingTaskId === task.task_id}
                                onClick={(e) => handleApproveTask(e, task)}
                                className={`flex-1 py-1 rounded text-white text-[10px] font-bold shadow-xs transition cursor-pointer flex items-center justify-center gap-1 ${
                                  approvingTaskId === task.task_id ? 'bg-[#059669]/70 cursor-not-allowed' : 'bg-[#059669] hover:bg-[#047857]'
                                }`}
                              >
                                {approvingTaskId === task.task_id ? (
                                  <>
                                    <div className="w-2.5 h-2.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                                    <span>Approving...</span>
                                  </>
                                ) : (
                                  <span>Approve (Zapier)</span>
                                )}
                              </button>
                              <button
                                type="button"
                                disabled={approvingTaskId === task.task_id}
                                onClick={(e) => handleRejectTask(e, task)}
                                className="px-2 py-1 rounded bg-white hover:bg-red-50 text-red-600 border border-red-200 text-[10px] font-semibold transition cursor-pointer"
                              >
                                Reject
                              </button>
                            </div>
                          </div>
                        )}

                        {/* Footer: Assignee & Quick Status Shift */}
                        <div className="pt-2.5 border-t border-[#E2E8F0] flex items-center justify-between">
                          <div className="flex items-center gap-2 min-w-0">
                            <div className="w-6 h-6 rounded-lg bg-gradient-to-tr from-[#2563EB] to-[#7C3AED] flex items-center justify-center text-white text-[10px] font-bold uppercase flex-shrink-0 shadow-xs">
                              {task.assigned_member_name ? task.assigned_member_name.slice(0, 2) : 'UN'}
                            </div>
                            <div className="min-w-0">
                              <p className="text-[11px] font-semibold text-[#0F172A] truncate">
                                {task.assigned_member_name || 'Unassigned'}
                              </p>
                              <p className="text-[9px] text-[#64748B] truncate">
                                {task.assigned_member_role || 'No role'}
                              </p>
                            </div>
                          </div>

                          {/* Quick Shift Controls */}
                          <div className="flex items-center gap-1">
                            {col.id === 'To Do' && (
                              <button
                                type="button"
                                title="Move to In Progress"
                                onClick={(e) => handleQuickStatusMove(e, task, 'In Progress')}
                                className="p-1 rounded-md text-[#64748B] hover:text-[#2563EB] hover:bg-[#EFF6FF] transition cursor-pointer"
                              >
                                <ChevronRight className="w-4 h-4" />
                              </button>
                            )}
                            {col.id === 'In Progress' && (
                              <>
                                <button
                                  type="button"
                                  title="Move to To Do"
                                  onClick={(e) => handleQuickStatusMove(e, task, 'To Do')}
                                  className="p-1 rounded-md text-[#64748B] hover:text-amber-600 hover:bg-amber-50 transition cursor-pointer"
                                >
                                  <ChevronLeft className="w-4 h-4" />
                                </button>
                                <button
                                  type="button"
                                  title="Move to Review"
                                  onClick={(e) => handleQuickStatusMove(e, task, 'Review')}
                                  className="p-1 rounded-md text-[#64748B] hover:text-[#7C3AED] hover:bg-[#F5F3FF] transition cursor-pointer"
                                >
                                  <ChevronRight className="w-4 h-4" />
                                </button>
                              </>
                            )}
                            {col.id === 'Review' && (
                              <>
                                <button
                                  type="button"
                                  title="Move back to In Progress"
                                  onClick={(e) => handleQuickStatusMove(e, task, 'In Progress')}
                                  className="p-1 rounded-md text-[#64748B] hover:text-[#2563EB] hover:bg-[#EFF6FF] transition cursor-pointer"
                                >
                                  <ChevronLeft className="w-4 h-4" />
                                </button>
                                {task.approval_status?.toLowerCase() === 'approved' && (
                                  (task.assigned_member_email || '').toLowerCase() === (user?.email || '').toLowerCase()
                                ) && (
                                  <button
                                    type="button"
                                    title="Mark as Completed"
                                    onClick={(e) => handleQuickStatusMove(e, task, 'Completed')}
                                    className="p-1 rounded-md text-[#64748B] hover:text-[#059669] hover:bg-[#ECFDF5] transition cursor-pointer"
                                  >
                                    <CheckCircle2 className="w-4 h-4 text-[#059669]" />
                                  </button>
                                )}
                              </>
                            )}
                            {col.id === 'Completed' && (
                              <button
                                type="button"
                                title="Move back to Review"
                                onClick={(e) => handleQuickStatusMove(e, task, 'Review')}
                                className="p-1 rounded-md text-[#64748B] hover:text-[#7C3AED] hover:bg-[#F5F3FF] transition cursor-pointer"
                              >
                                <ChevronLeft className="w-4 h-4" />
                              </button>
                            )}
                          </div>
                        </div>
                      </SortableTaskCard>
                        ))}
                        {isOver && (
                          <div className="py-4 text-center text-[11px] font-semibold text-[#2563EB] border border-dashed border-[#2563EB] rounded-xl bg-[#EFF6FF]/60">
                            Drop here to move to {col.label}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                  </SortableContext>
                </DroppableKanbanColumn>
              );
            })}
          </div>
          <DragOverlay>
            {activeDragTask ? (
              <div className="p-4 rounded-xl bg-white border-2 border-[#2563EB] shadow-2xl space-y-2 w-72 rotate-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-mono font-semibold text-[#2563EB]">{activeDragTask.task_id}</span>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${getPriorityBadgeClass(activeDragTask.priority)}`}>
                    {activeDragTask.priority}
                  </span>
                </div>
                <h4 className="text-xs font-bold text-[#0F172A] line-clamp-2">{activeDragTask.title}</h4>
              </div>
            ) : null}
          </DragOverlay>
        </DndContext>
      ) : (
        /* Table View */
        <div className="rounded-2xl bg-white border border-[#E2E8F0] overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#F8FAFC] text-[#64748B] uppercase text-[11px] tracking-wider border-b border-[#E2E8F0]">
                <tr>
                  <th className="px-5 py-3.5">Task ID</th>
                  <th className="px-5 py-3.5">Title & Description</th>
                  <th className="px-5 py-3.5">Assignee</th>
                  <th className="px-5 py-3.5">Priority</th>
                  <th className="px-5 py-3.5">Status</th>
                  <th className="px-5 py-3.5">Meeting</th>
                  <th className="px-5 py-3.5">Deadline</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E2E8F0]">
                {tasks.map((task) => (
                  <tr
                    key={task.task_id}
                    onClick={() => openTaskDetails(task)}
                    className="hover:bg-[#F8FAFC] transition cursor-pointer"
                  >
                    <td className="px-5 py-4 font-mono font-semibold text-[#2563EB]">
                      {task.task_id}
                    </td>
                    <td className="px-5 py-4 max-w-sm">
                      <p className="font-semibold text-[#0F172A]">{task.title}</p>
                      <p className="text-[11px] text-[#64748B] line-clamp-1 mt-0.5">{task.description}</p>
                    </td>
                    <td className="px-5 py-4">
                      <p className="font-medium text-[#0F172A]">{task.assigned_member_name}</p>
                      <span className="text-[10px] text-[#64748B]">{task.assigned_member_role}</span>
                    </td>
                    <td className="px-5 py-4">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${getPriorityBadgeClass(task.priority)}`}>
                        {task.priority}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${
                        task.status === 'Completed' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' :
                        task.status === 'In Progress' ? 'bg-[#EFF6FF] text-[#2563EB] border border-[#BFDBFE]' :
                        task.status === 'Review' ? 'bg-[#F5F3FF] text-[#7C3AED] border border-[#DDD6FE]' :
                        'bg-amber-50 text-amber-700 border border-amber-200'
                      }`}>
                        {task.status}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-[#64748B] max-w-xs truncate">
                      {task.meeting_title || 'General'}
                    </td>
                    <td className="px-5 py-4 text-[#64748B]">
                      {task.deadline || 'No deadline'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Modals */}
      <TaskDetailsModal
        isOpen={isDetailsOpen}
        onClose={() => setIsDetailsOpen(false)}
        task={selectedTask}
        onTaskUpdated={fetchTasks}
        onTaskDeleted={fetchTasks}
        teamMembers={teamMembers}
      />

      <CreateTaskModal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onTaskCreated={fetchTasks}
        teamMembers={teamMembers}
      />
    </div>
  );
}
