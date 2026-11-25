# MeetMind AI – Intelligent Multi-Agent Meeting Intelligence & Task Management Platform

MeetMind AI is a full-stack, enterprise-grade meeting intelligence platform. It captures live audio or uploaded recordings, transcribes multi-speaker conversations using Whisper STT, identifies speaker turn signatures, synthesizes structured meeting summaries with Groq LLaMA 3.3, extracts actionable deliverables, and intelligently assigns tasks to team members based on their verified technical skills, roles, and real-time workload capacity in MongoDB Atlas.

---

## Architecture & Technology Stack

### Frontend
- **Framework:** React 19 + Vite
- **Styling:** Tailwind CSS (White SaaS Theme: `#FFFFFF`, `#F8FAFC`, `#2563EB`, `#7C3AED`, `#059669`)
- **Routing:** React Router v7
- **HTTP Client:** Axios with JWT interceptors
- **Icons & Visuals:** Lucide React, Recharts

### Backend
- **Framework:** FastAPI (Python 3.11)
- **Validation:** Pydantic v2
- **Server:** Uvicorn (ASGI)
- **Authentication:** JWT (HMAC-SHA256) & Passlib (Bcrypt)
- **Async Client & Webhooks:** HTTPX with retry backoff & idempotency verification
- **Reporting:** ReportLab PDF Generation

### Database
- **Engine:** MongoDB Atlas (`meetmind_ai`)
- **Key Collections:**
  - `users`: Authentication & account profiles
  - `member_profiles`: Skills, roles, availability, and active workload tracking
  - `meetings`: Meeting metadata, audio file path, transcripts, speaker mappings, and summaries
  - `meeting_segments`: Diarized timestamped speech segments
  - `tasks`: Native task tracking with approval workflow and Kanban columns (`To Do`, `In Progress`, `Review`, `Completed`)
  - `automation_logs`: Webhook delivery telemetry, payloads, status codes, and idempotency records

### Agentic AI Pipeline (LangGraph 8-Agent Architecture)
1. **Agent 1: Audio Capture Agent** — Accepts browser `MediaRecorder` audio blobs or uploaded recordings (`.mp3`, `.wav`, `.m4a`, `.webm`, `.ogg`), enforces 50MB limits, stores in secure `uploads/` directory.
2. **Agent 2: Transcription Agent** — Converts speech to timestamped text via Groq Whisper API (`whisper-large-v3`).
3. **Agent 3: Speaker Diarization Agent** — Identifies speaker turns (`Speaker 1`, `Speaker 2`), provides acoustic clustering, and links to verified team member profiles.
4. **Agent 4: Meeting Analyst Agent** — Groq LLaMA 3.3 structured JSON extraction for executive summaries, core topics, and key decisions.
5. **Agent 5: Task Extraction Agent** — Identifies deliverables, explicit verbal ownership, deadlines, and urgency.
6. **Agent 6: Task Assignment Agent** — Matches deliverables against MongoDB `member_profiles` (skills matching, capacity limits, availability; verbal ownership takes priority).
7. **Agent 7: Review & Validation Agent** — Human-in-the-loop checkpoint ensuring tasks are queued in `Awaiting Approval` before creation.
8. **Agent 8: Automation Agent** — Securely triggers Zapier Webhook integrations upon explicit human approval.

### 5 Configured Zapier Workflows
- **Zap 1: Approved Task Notification (`task_approved`)**
  - Webhook: `https://hooks.zapier.com/hooks/catch/29528561/45lfwwd/`
  - Actions: Sends formatted Gmail alert to assignee, creates Trello card in Board list, logs row in Google Sheets.
- **Zap 2: Meeting Summary Automation (`meeting_completed`)**
  - Webhook: `https://hooks.zapier.com/hooks/catch/29528561/45lwq7z/`
  - Actions: Emails executive summary and decisions to team participants, appends row to Google Sheets Meeting Archive.
- **Zap 3: Task Deadline Reminder**
  - Schedule: Daily at 9:00 AM via Zapier Schedule.
  - Actions: Scans Google Sheets for tasks due within 24 hours, dispatches reminder emails via Gmail.
- **Zap 4: Task Completion Notification**
  - Trigger: Google Sheets row updated to `Status: Completed`.
  - Actions: Sends completion congratulations email to project manager via Gmail.
- **Zap 5: Team Member Welcome Automation (`team_member_added`)**
  - Webhook: `https://hooks.zapier.com/hooks/catch/29528561/45ll6l2/`
  - Actions: Sends personalized welcome email to new member via Gmail, updates Storage by Zapier directory.

---

## Getting Started & Local Setup

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm
- MongoDB Atlas cluster URI or local MongoDB (`mongodb://localhost:27017`)
- Groq API Key (for LLaMA 3.3 and Whisper)

### 1. Backend Setup
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Create `backend/.env`:
```env
MONGODB_URI="mongodb://localhost:27017"
DATABASE_NAME="meetmind_ai"
JWT_SECRET="meetmind-super-secure-jwt-secret-key-32chars-min-2026"
GROQ_API_KEY="your-groq-api-key"
ZAPIER_TASK_APPROVED_WEBHOOK_URL="https://hooks.zapier.com/hooks/catch/29528561/45lfwwd/"
ZAPIER_MEETING_COMPLETED_WEBHOOK_URL="https://hooks.zapier.com/hooks/catch/29528561/45lwq7z/"
ZAPIER_TEAM_MEMBER_ADDED_WEBHOOK_URL="https://hooks.zapier.com/hooks/catch/29528561/45ll6l2/"
```

Start the FastAPI server:
```powershell
cd backend
.\.venv\Scripts\uvicorn app.main:app --reload --port 8000
```
Interactive API docs are available at `http://localhost:8000/docs`.

### 2. Frontend Setup
```powershell
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## Running Verification Tests

Run the full pytest suite (16 integration and unit tests covering meetings, tasks, team registrations, LangGraph execution, and Zapier webhook dispatch):
```powershell
cd backend
$env:PYTHONPATH="."
.\.venv\Scripts\python -m pytest tests/ -v
```

Build the React production bundle:
```powershell
cd frontend
npm run build
```

---

## Deployment Guide

### Backend: Render
1. Create a **New Web Service** connected to your repository.
2. Root Directory: `backend`
3. Environment: `Python 3`
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. Add Environment Variables: `MONGODB_URI`, `DATABASE_NAME`, `JWT_SECRET`, `GROQ_API_KEY`, and the three `ZAPIER_*_WEBHOOK_URL` variables.

### Frontend: Vercel
1. Create a **New Project** importing the repository.
2. Root Directory: `frontend`
3. Framework Preset: `Vite`
4. Build Command: `npm run build`
5. Output Directory: `dist`
6. Add Environment Variable: `VITE_API_URL` pointing to your deployed Render backend (e.g. `https://meetmind-api.onrender.com/api`).
