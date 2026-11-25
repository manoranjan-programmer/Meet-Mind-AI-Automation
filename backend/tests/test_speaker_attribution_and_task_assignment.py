import pytest
from app.agents.diarization_agent import DiarizationAgent
from app.agents.task_extraction_agent import TaskExtractionAgent
from app.agents.task_assignment_agent import TaskAssignmentAgent

def test_conversational_speaker_attribution_and_task_assignment():
    # 1. Active meeting attendees
    participants = [
        {"member_id": "mem_001", "name": "Jai Prakash", "email": "jai@meetmind.ai", "role": "Frontend Developer", "skills": ["React", "JavaScript", "Tailwind CSS"]},
        {"member_id": "mem_002", "name": "Arun Kumar", "email": "arun@meetmind.ai", "role": "Backend Engineer", "skills": ["Python", "FastAPI", "MongoDB"]}
    ]

    # 2. Raw speech segments where speakers verbally identify or speak
    segments = [
        {"text": "Jai: I will develop the login page and registration UI using React and Tailwind CSS."},
        {"text": "Arun: I will build the authentication APIs and MongoDB database integration using FastAPI."}
    ]

    # Test Diarization Agent
    diar_res = DiarizationAgent.execute(segments=segments, participants=participants)
    assert diar_res["status"] == "success"
    diar_segments = diar_res["diarized_segments"]
    assert len(diar_segments) == 2
    assert diar_segments[0]["speaker_label"] == "Jai"
    assert diar_segments[1]["speaker_label"] == "Arun"

    # Test Task Extraction Agent
    ext_res = TaskExtractionAgent.execute(
        transcript_text="Jai: I will develop the login page and registration UI.\nArun: I will build the authentication APIs.",
        diarized_segments=diar_segments
    )
    assert ext_res["status"] == "success"
    tasks = ext_res["extracted_tasks"]
    assert len(tasks) >= 2

    # Verify explicit owner extracted correctly
    jai_task = next((t for t in tasks if "login" in t["title"].lower()), None)
    arun_task = next((t for t in tasks if "auth" in t["title"].lower() or "api" in t["title"].lower()), None)

    assert jai_task is not None
    assert jai_task["explicit_owner"] == "Jai"

    assert arun_task is not None
    assert arun_task["explicit_owner"] == "Arun"

    # Test Task Assignment Agent
    assign_res = TaskAssignmentAgent.execute(
        team_id="team_demo",
        extracted_tasks=[jai_task, arun_task],
        selected_participant_ids=["mem_001", "mem_002"],
        participants=participants
    )
    assert assign_res["status"] == "success"
    assigned = assign_res["assigned_tasks"]

    # Verify Jai's task is assigned to Jai Prakash
    assigned_jai = next(a for a in assigned if "login" in a["title"].lower())
    assert assigned_jai["assigned_member_id"] == "mem_001"
    assert "Jai" in assigned_jai["assigned_member_name"]
    assert assigned_jai["confidence_score"] >= 0.95

    # Verify Arun's task is assigned to Arun Kumar
    assigned_arun = next(a for a in assigned if "auth" in a["title"].lower() or "api" in a["title"].lower())
    assert assigned_arun["assigned_member_id"] == "mem_002"
    assert "Arun" in assigned_arun["assigned_member_name"]
    assert assigned_arun["confidence_score"] >= 0.95
