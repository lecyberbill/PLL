from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional

# --- Project ---
class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    disk_path: str = ""  # absolute path on disk, empty = DB mode

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    disk_path: Optional[str] = None

class ProjectOut(BaseModel):
    id: int
    name: str
    description: str
    disk_path: str = ""
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

# --- Artifact ---
class ArtifactCreate(BaseModel):
    path: str = Field(..., min_length=1, max_length=500)
    content: str = ""

class ArtifactUpdate(BaseModel):
    content: str

class ArtifactOut(BaseModel):
    id: int
    project_id: int
    path: str
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

# --- AgentSession ---
class AgentSessionCreate(BaseModel):
    project_id: int
    generation: int = 0
    agent_type: str = "primary"  # primary | shadow
    objective: str = ""
    current_state: str = ""

class AgentSessionStatusUpdate(BaseModel):
    status: str  # born | working | documenting | completed | dead
    current_state: Optional[str] = None

class AgentSessionOut(BaseModel):
    id: int
    project_id: int
    generation: int
    agent_type: str
    status: str
    objective: str
    current_state: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

# --- GCA Vault ---
class GCAVaultEntryCreate(BaseModel):
    project_id: int
    session_id: Optional[int] = None
    key: str
    content: str

class GCAVaultEntryOut(BaseModel):
    id: int
    project_id: int
    session_id: Optional[int]
    key: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}

# --- GCA Operations ---
class GCAInitResponse(BaseModel):
    project_id: int
    primary_session: AgentSessionOut
    shadow_session: AgentSessionOut

class GCACheckpointCreate(BaseModel):
    project_id: int
    session_id: int
    key: str
    content: str
    current_state: str

class GCAHandoffResponse(BaseModel):
    old_primary: AgentSessionOut
    new_primary: AgentSessionOut
    new_shadow: AgentSessionOut
    vault_summary: str

class GCASummary(BaseModel):
    project_id: int
    total_generations: int
    current_primary: Optional[AgentSessionOut]
    current_shadow: Optional[AgentSessionOut]
    vault_entries_count: int

# --- Package ---
class PackageCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    source_content: str = ""

class PackageOut(BaseModel):
    id: int
    name: str
    version: str
    description: str
    author: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class PackageDetailOut(PackageOut):
    source_content: str

# --- PLL Message Wrapper ---
class PLLMessage(BaseModel):
    sender: str
    receiver: str
    message_type: str  # objective | state | handoff | checkpoint | artifact
    payload: str
    generation: int = 0
