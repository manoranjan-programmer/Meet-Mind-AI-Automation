import pytest
import uuid
import httpx
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.database.mongo import get_col

client = TestClient(app)

@pytest.fixture
def team_lead_auth():
    suffix = uuid.uuid4().hex[:6]
    email = f"team_lead_{suffix}@meetmind.ai"
    password = "SuperSecurePassword123!"

    reg_res = client.post("/api/auth/register", json={
        "name": f"Team Lead {suffix}",
        "email": email,
        "password": password,
        "team_name": f"Workspace {suffix}",
        "role": "Team Lead"
    })
    assert reg_res.status_code in [200, 201]
    data = reg_res.json()
    token = data["access_token"]
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "email": email,
        "team_id": data["user"]["team_id"],
        "suffix": suffix
    }

def test_team_lead_can_invite_editor_and_viewer(team_lead_auth):
    """Test 1 & 2: Team leader invites new email as Editor and another as Viewer."""
    suffix = uuid.uuid4().hex[:6]
    editor_email = f"editor_{suffix}@example.com"
    viewer_email = f"viewer_{suffix}@example.com"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"status": "success"}'

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        # 1. Invite Editor
        res1 = client.post("/api/team/invitations", json={
            "email": editor_email,
            "role": "Editor",
            "message": "Welcome as Editor"
        }, headers=team_lead_auth["headers"])
        assert res1.status_code == 201
        inv1 = res1.json()
        assert inv1["assigned_role"] == "Editor"
        assert inv1["status"] == "pending"
        assert inv1["raw_token"] is not None

        # 2. Invite Viewer
        res2 = client.post("/api/team/invitations", json={
            "email": viewer_email,
            "role": "Viewer"
        }, headers=team_lead_auth["headers"])
        assert res2.status_code == 201
        inv2 = res2.json()
        assert inv2["assigned_role"] == "Viewer"
        assert inv2["status"] == "pending"

def test_cannot_invite_duplicate_pending_or_active(team_lead_auth):
    """Verify duplicate pending invitation is blocked with 409."""
    suffix = uuid.uuid4().hex[:6]
    dup_email = f"dup_{suffix}@example.com"

    # First invite
    res1 = client.post("/api/team/invitations", json={
        "email": dup_email,
        "role": "Editor"
    }, headers=team_lead_auth["headers"])
    assert res1.status_code == 201

    # Second invite to same email
    res2 = client.post("/api/team/invitations", json={
        "email": dup_email,
        "role": "Viewer"
    }, headers=team_lead_auth["headers"])
    assert res2.status_code == 409
    assert "pending invitation already exists" in res2.json()["detail"].lower()

def test_invitation_token_validation_and_acceptance(team_lead_auth):
    """Test 3, 4, 5, 6: Validation, user registration, single-use token, active membership."""
    suffix = uuid.uuid4().hex[:6]
    invited_email = f"member_{suffix}@example.com"

    # 1. Team leader invites member
    inv_res = client.post("/api/team/invitations", json={
        "email": invited_email,
        "role": "Editor"
    }, headers=team_lead_auth["headers"])
    assert inv_res.status_code == 201
    raw_token = inv_res.json()["raw_token"]

    # 2. Public validate endpoint
    val_res = client.get(f"/api/invitations/validate/{raw_token}")
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert val_data["is_valid"] is True
    assert val_data["invited_email"] == invited_email
    assert val_data["assigned_role"] == "Editor"

    # 3. Teammate accepts invitation & registers
    accept_res = client.post("/api/invitations/accept", json={
        "token": raw_token,
        "name": f"Jane Editor {suffix}",
        "password": "Password123!",
        "skills": ["React", "TypeScript"]
    })
    assert accept_res.status_code == 201
    member = accept_res.json()
    assert member["email"] == invited_email
    assert member["role"] == "Editor"
    assert member["account_status"] == "active"

    # 4. Single-use token enforcement: trying to accept again should fail
    reaccept_res = client.post("/api/invitations/accept", json={
        "token": raw_token,
        "name": "Jane Again",
        "password": "Password123!"
    })
    assert reaccept_res.status_code == 400
    assert "already been accepted" in reaccept_res.json()["detail"].lower()

def test_wrong_email_cannot_accept_another_invitation(team_lead_auth):
    """Test 9: Authenticated user with different email cannot accept someone else's invitation."""
    suffix = uuid.uuid4().hex[:6]
    invited_email = f"alice_{suffix}@example.com"
    intruder_email = f"bob_{suffix}@example.com"

    # 1. Invite Alice
    inv_res = client.post("/api/team/invitations", json={
        "email": invited_email,
        "role": "Editor"
    }, headers=team_lead_auth["headers"])
    raw_token = inv_res.json()["raw_token"]

    # 2. Register Bob
    bob_reg = client.post("/api/auth/register", json={
        "name": "Bob Intruder",
        "email": intruder_email,
        "password": "Password123!",
        "team_name": "Bob's Team"
    })
    bob_token = bob_reg.json()["access_token"]

    # 3. Bob attempts to accept Alice's invitation using his token
    bob_accept = client.post("/api/invitations/accept", json={
        "token": raw_token,
        "name": "Bob Intruder"
    }, headers={"Authorization": f"Bearer {bob_token}"})
    assert bob_accept.status_code == 403
    assert "does not match the invited email" in bob_accept.json()["detail"].lower()

def test_rbac_viewer_cannot_modify_tasks_or_invite(team_lead_auth):
    """Test 7 & 8: Viewer permissions vs Editor/Admin."""
    suffix = uuid.uuid4().hex[:6]
    viewer_email = f"viewer_{suffix}@example.com"

    # 1. Invite and accept as Viewer
    inv_res = client.post("/api/team/invitations", json={
        "email": viewer_email,
        "role": "Viewer"
    }, headers=team_lead_auth["headers"])
    raw_token = inv_res.json()["raw_token"]

    client.post("/api/invitations/accept", json={
        "token": raw_token,
        "name": f"Viewer Person {suffix}",
        "password": "Password123!"
    })

    # Log in as Viewer
    login_res = client.post("/api/auth/login", json={
        "email": viewer_email,
        "password": "Password123!"
    })
    viewer_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # Viewer CAN view tasks
    get_tasks = client.get("/api/tasks", headers=viewer_headers)
    assert get_tasks.status_code == 200

    # Viewer CANNOT create task
    post_task = client.post("/api/tasks", json={
        "title": "Forbidden Viewer Task",
        "priority": "Low"
    }, headers=viewer_headers)
    assert post_task.status_code == 403

    # Viewer CANNOT invite members
    invite_res = client.post("/api/team/invitations", json={
        "email": "someone@example.com",
        "role": "Editor"
    }, headers=viewer_headers)
    assert invite_res.status_code == 403
