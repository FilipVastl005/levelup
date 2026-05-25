import builtins
from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Column, JSON
from datetime import datetime
import uuid

def generate_uuid():
    return str(uuid.uuid4())

class User(SQLModel, table=True):
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    email: str = Field(unique=True, index=True)
    password: str  # Will store bcrypt hash
    username: str
    total_xp: int = Field(default=0)
    physical_xp: int = Field(default=0)
    sharpness_xp: int = Field(default=0)
    wellbeing_xp: int = Field(default=0)
    physical_level: int = Field(default=1)
    sharpness_level: int = Field(default=1)
    wellbeing_level: int = Field(default=1)
    total_level: int = Field(default=1)
    current_streak: int = Field(default=0)
    physical_baseline: int = Field(default=5)
    sharpness_baseline: int = Field(default=5)
    wellbeing_baseline: int = Field(default=5)
    onboarding_done: bool = Field(default=False)
    theme: str = Field(default="light")
    last_log_date: Optional[str] = Field(default=None) # ISO format date string
    created: datetime = Field(default_factory=datetime.utcnow)
    updated: datetime = Field(default_factory=datetime.utcnow)

class Log(SQLModel, table=True):
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    user_id: str = Field(index=True)
    category: str
    description: str
    xp_awarded: int
    ai_response: str
    verified: bool
    created: datetime = Field(default_factory=datetime.utcnow)
    updated: datetime = Field(default_factory=datetime.utcnow)

class Friend(SQLModel, table=True):
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    user_id: str = Field(index=True)
    friend_id: str = Field(index=True)
    status: str = Field(default="pending") # pending, accepted
    created: datetime = Field(default_factory=datetime.utcnow)
    updated: datetime = Field(default_factory=datetime.utcnow)

class Group(SQLModel, table=True):
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    name: str
    created_by: str
    member_ids: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    created: datetime = Field(default_factory=datetime.utcnow)
    updated: datetime = Field(default_factory=datetime.utcnow)

class QueueItem(SQLModel, table=True):
    __tablename__ = "queue"
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    job_id: str = Field(unique=True, index=True)
    user_id: str
    category: str
    description: str
    status: str = Field(default="pending") # pending, processing, completed, failed
    xp_awarded: int = Field(default=0)
    ai_response: str = Field(default="")
    verified: bool = Field(default=False)
    created: datetime = Field(default_factory=datetime.utcnow)
    updated: datetime = Field(default_factory=datetime.utcnow)

class Feedback(SQLModel, table=True):
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    user_id: str
    queue_id: str
    message: str
    reviewed: bool = Field(default=False)
    created: datetime = Field(default_factory=datetime.utcnow)
    updated: datetime = Field(default_factory=datetime.utcnow)
