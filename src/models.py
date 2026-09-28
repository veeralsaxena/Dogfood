from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any

class ProjectCreate(BaseModel):
    title: str
    summary: Optional[str] = ""
    description: Optional[str] = ""
    repo_url: Optional[str] = None
    demo_url: Optional[str] = None
    track_id: Optional[str] = None
    team_id: Optional[str] = None
    is_draft: Optional[bool] = False

class ProjectResponse(BaseModel):
    id: str
    title: str
    summary: Optional[str] = ""
    repo_url: Optional[str] = None
    demo_url: Optional[str] = None
    track_id: Optional[str] = None
    team_id: Optional[str] = None
    submitted_at: str

class ScoreCreate(BaseModel):
    project_id: str
    criteria: Dict[str, int]
    comment: Optional[str] = ""

class PairwiseVoteCreate(BaseModel):
    winner_id: str
    loser_id: str

class CommentCreate(BaseModel):
    content: str
    author_name: Optional[str] = "Anonymous"

class CommunityVoteCreate(BaseModel):
    project_id: str

class EventCreate(BaseModel):
    id: str
    name: str
    submissions_close: str
    weights: Optional[Dict[str, float]] = None
