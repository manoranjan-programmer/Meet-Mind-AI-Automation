import React from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import AppLayout from './layouts/AppLayout';
import LandingPage from './pages/LandingPage';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import DashboardPage from './pages/DashboardPage';
import TeamWorkspacePage from './pages/TeamWorkspacePage';
import WorkspaceChatPage from './pages/WorkspaceChatPage';
import TeamPage from './pages/TeamPage';
import AcceptInvitationPage from './pages/AcceptInvitationPage';
import LiveMeetingPage from './pages/LiveMeetingPage';
import UpcomingMeetingsPage from './pages/UpcomingMeetingsPage';
import MeetingsPage from './pages/MeetingsPage';
import TasksPage from './pages/TasksPage';
import AutomationCenterPage from './pages/AutomationCenterPage';
import AIAgentsPage from './pages/AIAgentsPage';
import AnalyticsPage from './pages/AnalyticsPage';
import SettingsPage from './pages/SettingsPage';

function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen bg-[#F8FAFC] flex items-center justify-center text-xs text-[#64748B] font-medium">
        <div className="w-5 h-5 border-2 border-[#2563EB] border-t-transparent rounded-full animate-spin mr-2.5" />
        Loading MeetMind AI session...
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: `${location.pathname}${location.search}` }} replace />;
  }

  return children;
}

export default function App() {
  return (
    <Routes>
      {/* Public Pages */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/accept-invitation" element={<AcceptInvitationPage />} />
      <Route path="/accept-invitation/:token" element={<AcceptInvitationPage />} />

      {/* Protected App Pages */}
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/workspace" element={<TeamWorkspacePage />} />
        <Route path="/chat" element={<WorkspaceChatPage />} />
        <Route path="/team" element={<TeamPage />} />
        <Route path="/live-meeting" element={<LiveMeetingPage />} />
        <Route path="/upcoming-meetings" element={<UpcomingMeetingsPage />} />
        <Route path="/meetings" element={<MeetingsPage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/tasks/:taskId" element={<TasksPage />} />
        <Route path="/automation" element={<AutomationCenterPage />} />
        <Route path="/agents" element={<AIAgentsPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
