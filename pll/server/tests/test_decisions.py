import pytest
import sys, os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from models import AgentSession, Conversation
from services.agent_brain import sync_decision_tree

class DummyDB:
    def __init__(self):
        self.added = []
    def add(self, item):
        self.added.append(item)
    async def commit(self):
        pass
    async def flush(self):
        pass
    async def refresh(self, obj):
        pass

@pytest.mark.anyio
async def test_sync_decision_tree():
    session = AgentSession(
        project_id=1,
        agent_type="primary",
        status="active",
        current_state=""
    )
    
    conv_msgs = [
        Conversation(role="user", content="Je veux une API Flask"),
        Conversation(role="assistant", content="QUESTION: Quelle base de données ? SQLite ou PostgreSQL ?"),
        Conversation(role="user", content="Utilise SQLite")
    ]
    
    db = DummyDB()
    import services.llm_proxy as lp
    original_chat_completion = lp.chat_completion
    
    async def mock_chat_completion(*args, **kwargs):
        return {
            "response": """
[
  {"question": "Quelle base de données ?", "answer": "SQLite", "status": "active"}
]
"""
        }
    
    lp.chat_completion = mock_chat_completion
    try:
        await sync_decision_tree(session, "Utilise SQLite", conv_msgs, db, "test")
    finally:
        lp.chat_completion = original_chat_completion
        
    assert "SQLite" in session.current_state
    assert len(db.added) == 1
    assert db.added[0].key == "session_None_decisions.md"
    assert "SQLite" in db.added[0].content

from services.agent_coordinator import AgentCoordinator

@pytest.mark.anyio
async def test_capability_routing():
    coord = AgentCoordinator(project_id=1, backend="test")
    storage_inst = coord._get_capability_instructions("StorageCap")
    assert "database" in storage_inst
    
    ui_inst = coord._get_capability_instructions("UiCap")
    assert "user interface" in ui_inst

from services.agent_brain import AgentBrain
from models import GCAVault

@pytest.mark.anyio
async def test_semantic_rag():
    class MockResult:
        def __init__(self, items):
            self.items = items
        def scalars(self):
            return self
        def all(self):
            return self.items

    class MockDB:
        def __init__(self, entries):
            self.entries = entries
        async def execute(self, query):
            return MockResult(self.entries)

    entries = [
        GCAVault(project_id=1, key="v1.pll", content='**Request:** "Save user"\ncode: "..."'),
        GCAVault(project_id=1, key="v2.pll", content='**Request:** "Render HTML page"\ncode: "..."')
    ]
    
    db = MockDB(entries)
    brain = AgentBrain(db)
    
    import services.agent_brain as ab
    original_chat_completion = ab.chat_completion
    
    async def mock_chat_completion(*args, **kwargs):
        return {"response": "[1]"}
        
    ab.chat_completion = mock_chat_completion
    try:
        res = await brain._retrieve_similar_examples(project_id=1, query="Render HTML", top_k=1, backend="test")
    finally:
        ab.chat_completion = original_chat_completion
        
    assert len(res) == 1
    assert res[0]["key"] == "v2.pll"


