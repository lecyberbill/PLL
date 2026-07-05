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
