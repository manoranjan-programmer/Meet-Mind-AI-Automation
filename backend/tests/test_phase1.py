import pytest
import io
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.database.mongo import get_col, get_database

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_complete_phase1_flow():
    # 1. Register an Admin User
    unique_suffix = uuid.uuid4().hex[:6]
    admin_email = f"admin_{unique_suffix}@meetmind.ai"
    reg_payload = {
        "name": "Sarah Connor",
        "email": admin_email,
        "password": "Password123!",
        "team_name": f"Cyberdyne Team {unique_suffix}",
        "role": "Team Lead"
    }
    reg_res = client.post("/api/auth/register", json=reg_payload)
    assert reg_res.status_code == 200, f"Register failed: {reg_res.text}"
    auth_data = reg_res.json()
    token = auth_data["access_token"]
    team_id = auth_data["user"]["team_id"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify admin was registered in member_profiles
    member_col = get_col("member_profiles")
    admin_member = member_col.find_one({"team_id": team_id, "email": admin_email.lower()})
    assert admin_member is not None
    assert admin_member["registration_method"] == "manual"
    assert admin_member["account_status"] == "active"

    # 2. METHOD 1: ADMIN MANUAL REGISTRATION
    # Jai – Frontend Developer – React, JavaScript, CSS
    jai_email = f"jai_{unique_suffix}@example.com"
    manual_payload = {
        "name": "Jai",
        "email": jai_email,
        "role": "Frontend Developer",
        "skills": ["React", "JavaScript", "HTML", "CSS"],
        "experience": "Intermediate",
        "availability": "Available",
        "maximum_workload": 5
    }
    manual_res = client.post("/api/team/members", json=manual_payload, headers=headers)
    assert manual_res.status_code == 201, f"Manual add failed: {manual_res.text}"
    jai_data = manual_res.json()
    assert jai_data["name"] == "Jai"
    assert jai_data["registration_method"] == "manual"
    assert jai_data["account_status"] == "active"

    # Verify duplicate prevention in same team
    dup_res = client.post("/api/team/members", json=manual_payload, headers=headers)
    assert dup_res.status_code == 409

    # 3. METHOD 2: CSV BULK IMPORT
    # CSV content with Arun, Priya, Karthik and one duplicate
    csv_text = f"""name,email,role,skills,experience,availability,maximum_workload
Arun,arun_{unique_suffix}@example.com,Backend Developer,"Python,Node.js,MongoDB",Advanced,Available,5
Priya,priya_{unique_suffix}@example.com,UI/UX Designer,"Figma,UI Design",Intermediate,Busy,3
Karthik,karthik_{unique_suffix}@example.com,Tester,"Selenium,Testing",Intermediate,Available,5
DuplicateJai,{jai_email},Frontend Developer,React,Junior,Available,3
"""
    files = {"file": ("test_members.csv", csv_text.encode("utf-8"), "text/csv")}
    import_res = client.post("/api/team/members/import?preview=false", files=files, headers=headers)
    assert import_res.status_code == 200, f"Import failed: {import_res.text}"
    import_data = import_res.json()
    assert import_data["valid_count"] == 3
    assert import_data["invalid_count"] == 1
    assert import_data["imported_count"] == 3
    assert any("already exists" in inv["error"] for inv in import_data["invalid_rows"])

    # Verify Arun was stored as a pending invitation (Section 8: CSV import creates pending invitations)
    inv_col = get_col("team_invitations")
    arun_inv = inv_col.find_one({"team_id": team_id, "invited_email": f"arun_{unique_suffix}@example.com"})
    assert arun_inv is not None
    assert arun_inv["invitation_status"] == "pending"

    # Accept invitations for Arun, Priya, and Karthik to test onboarding and activate them
    for name, email, skills, avail in [
        ("Arun", f"arun_{unique_suffix}@example.com", ["Python", "Node.js", "MongoDB"], "Available"),
        ("Priya", f"priya_{unique_suffix}@example.com", ["Figma", "UI Design"], "Busy"),
        ("Karthik", f"karthik_{unique_suffix}@example.com", ["Selenium", "Testing"], "Available"),
    ]:
        inv = inv_col.find_one({"team_id": team_id, "invited_email": email})
        raw_tok = inv["invitation_url"].split("/")[-1]
        acc_res = client.post("/api/team/accept-invitation", json={
            "token": raw_tok,
            "name": name,
            "password": "Password123!",
            "skills": skills,
            "availability": avail,
            "maximum_workload": 5
        })
        assert acc_res.status_code == 201

    # Verify Arun is now an active member
    arun_member = member_col.find_one({"team_id": team_id, "email": f"arun_{unique_suffix}@example.com"})
    assert arun_member is not None
    assert arun_member["registration_method"] == "invitation"
    assert "Python" in arun_member["skills"]
    assert "MongoDB" in arun_member["skills"]

    # 4. METHOD 3: INVITATION AND SELF-REGISTRATION
    invite_email = f"devops_{unique_suffix}@example.com"
    invite_payload = {
        "email": invite_email,
        "role": "DevOps Engineer"
    }
    invite_res = client.post("/api/team/invite", json=invite_payload, headers=headers)
    assert invite_res.status_code == 201, f"Invite failed: {invite_res.text}"
    invite_data = invite_res.json()
    assert invite_data["status"] == "pending"
    assert "raw_token" in invite_data
    raw_token = invite_data["raw_token"]

    # Check token in team_invitations collection is hashed
    inv_col = get_col("team_invitations")
    inv_doc = inv_col.find_one({"invitation_id": invite_data["invitation_id"]})
    assert inv_doc is not None
    assert inv_doc["token_hash"] != raw_token  # Hashed!

    # Public endpoint to inspect invitation info
    info_res = client.get(f"/api/team/invitation-info?token={raw_token}")
    assert info_res.status_code == 200
    info_data = info_res.json()
    assert info_data["is_valid"] is True
    assert info_data["email"] == invite_email
    assert info_data["role"] in ["Editor", "DevOps Engineer"]

    # Member self-registers via accept-invitation
    accept_payload = {
        "token": raw_token,
        "name": "Alex Mercer",
        "password": "AlexPassword123!",
        "skills": ["Docker", "Kubernetes", "AWS", "CI/CD"],
        "experience": "Senior",
        "availability": "Available",
        "maximum_workload": 5
    }
    accept_res = client.post("/api/team/accept-invitation", json=accept_payload)
    assert accept_res.status_code == 201, f"Accept invite failed: {accept_res.text}"
    accepted_data = accept_res.json()
    assert accepted_data["registration_method"] == "invitation"
    assert accepted_data["account_status"] == "active"

    # Check user account was created in `users`
    users_col = get_col("users")
    invited_user = users_col.find_one({"email": invite_email})
    assert invited_user is not None
    assert invited_user["hashed_password"] != "AlexPassword123!"

    # Verify invitation status was updated to "accepted"
    updated_inv = inv_col.find_one({"invitation_id": invite_data["invitation_id"]})
    assert updated_inv["status"] == "accepted"

    # Reusing the token should now fail
    reuse_res = client.post("/api/team/accept-invitation", json=accept_payload)
    assert reuse_res.status_code == 400

    # 5. TEST MEMBER CRUD, SEARCH, AND FILTERS
    # List all members
    list_res = client.get("/api/team/members", headers=headers)
    assert list_res.status_code == 200
    all_members = list_res.json()["members"]
    # Total: Sarah (Admin) + Jai (Manual) + Arun (CSV) + Priya (CSV) + Karthik (CSV) + Alex (Invite) = 6
    assert len(all_members) == 6

    # Search by skill: "React"
    search_res = client.get("/api/team/members?search=React", headers=headers)
    assert search_res.status_code == 200
    react_members = search_res.json()["members"]
    assert any(m["name"] == "Jai" for m in react_members)

    # Filter by availability: "Busy"
    busy_res = client.get("/api/team/members?availability=Busy", headers=headers)
    assert busy_res.status_code == 200
    busy_members = busy_res.json()["members"]
    assert any(m["name"] == "Priya" for m in busy_members)

    # Update Member Profile
    jai_id = jai_data["member_id"]
    update_res = client.put(
        f"/api/team/members/{jai_id}",
        json={"experience": "Senior", "availability": "Busy"},
        headers=headers
    )
    assert update_res.status_code == 200
    assert update_res.json()["experience"] == "Senior"
    assert update_res.json()["availability"] == "Busy"

    # Delete Member Profile
    del_res = client.delete(f"/api/team/members/{jai_id}", headers=headers)
    assert del_res.status_code == 200
    del_check = client.get(f"/api/team/members/{jai_id}", headers=headers)
    assert del_check.status_code == 404

    # 6. DASHBOARD STATS
    stats_res = client.get("/api/dashboard/stats", headers=headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["total_members"] == 5  # 6 - 1 deleted = 5
