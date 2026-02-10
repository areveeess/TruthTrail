from pydantic import BaseModel
from typing import Optional

class Event(BaseModel):
    event_id: str
    platform: str
    content_id: str
    parent_event_id: Optional[str]
    user_id: str
    timestamp: str
    user_influence: int