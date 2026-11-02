from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    media_url: Optional[str] = None
    link: Optional[str] = None
    source: str = "catalog"

class Product(ProductBase):
    id: Optional[int] = None
    status: str = "pending"  # pending | posted | failed
    posted_at: Optional[datetime] = None

class GroupBase(BaseModel):
    name: str
    url: Optional[str] = None
    category: Optional[str] = None

class Group(GroupBase):
    id: Optional[int] = None

class CampaignBase(BaseModel):
    name: str
    product_ids: List[int] = []
    group_ids: List[int] = []

class Campaign(CampaignBase):
    id: Optional[int] = None
    status: str = "idle"  # idle | running | completed | failed
    created_at: Optional[datetime] = None
    posts_sent: int = 0

class LogEntry(BaseModel):
    id: Optional[int] = None
    level: str = "info"
    message: str
    source: str = "bot"
    created_at: Optional[datetime] = None
