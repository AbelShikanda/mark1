import re
from pydantic import BaseModel, field_validator
from typing import Any, Dict, List, Optional
from datetime import datetime, date
from urllib.parse import urlparse

_PHONE_RE = re.compile(r"^\+?[0-9][0-9\s().-]{5,24}$")
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def _clean_url(value: Optional[str], label: str = "link") -> Optional[str]:
    """Normalise and validate a URL, accepting a missing http(s) scheme."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if not _SCHEME_RE.match(text):
        text = "https://" + text
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or "." not in parsed.netloc:
        raise ValueError(f"enter a valid {label} (for example https://example.com)")
    return text


def _clean_media_url(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Uploaded files are served from this app, so a relative path is valid.
    if text.startswith("/uploads/") or text.startswith("data:"):
        return text
    return _clean_url(text, "image URL")


def _clean_phone(value: Optional[str]) -> str:
    if value is None:
        raise ValueError("phone number is required")
    text = str(value).strip()
    digits = re.sub(r"\D", "", text)
    if not _PHONE_RE.match(text) or not (7 <= len(digits) <= 15):
        raise ValueError("enter a valid phone number (7-15 digits, optional + and spaces)")
    return text


class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    media_url: Optional[str] = None
    link: Optional[str] = None
    category: Optional[str] = None
    status: str = "isNotPosted"


class Product(ProductBase):
    id: Optional[int] = None
    posted_at: Optional[datetime] = None
    last_posted_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProductInput(ProductBase):
    """Write model: validates user-supplied links while response models stay lenient."""

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("name is required")
        return text

    @field_validator("link", mode="before")
    @classmethod
    def _link(cls, value):
        return _clean_url(value, "link")

    @field_validator("media_url", mode="before")
    @classmethod
    def _media_url(cls, value):
        return _clean_media_url(value)


class ProductStatusUpdate(BaseModel):
    status: str


class GroupBase(BaseModel):
    name: str
    category: Optional[str] = None
    location: Optional[str] = None
    n: int = 1
    link: Optional[str] = None
    is_my_group: bool = False
    is_core: bool = False


class Group(GroupBase):
    id: Optional[int] = None
    isPostedProductToday: int = 0
    failures: int = 0
    is_active: bool = True
    total_misses: int = 0
    is_silenced: bool = False
    silenced_at: Optional[str] = None
    silence_reason: Optional[str] = None
    last_missed_at: Optional[str] = None
    last_success_at: Optional[str] = None


class GroupInput(GroupBase):
    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("name is required")
        return text

    @field_validator("link", mode="before")
    @classmethod
    def _link(cls, value):
        return _clean_url(value, "group link")


class OriginGroup(BaseModel):
    """A myGroupLink source: the group whose invite link is being promoted."""

    id: Optional[int] = None
    name: Optional[str] = None
    link: Optional[str] = None


class ClientBase(BaseModel):
    name: str
    number: str
    category: Optional[str] = None
    location: Optional[str] = None
    birthdays: Optional[str] = None

    @field_validator("birthdays", mode="before")
    @classmethod
    def _birthdays(cls, value):
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            raise ValueError("birthday must be a valid date (YYYY-MM-DD)")


class Client(ClientBase):
    id: Optional[int] = None


class ClientInput(ClientBase):
    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("name is required")
        return text

    @field_validator("number", mode="before")
    @classmethod
    def _number(cls, value):
        return _clean_phone(value)


class GroupBatchBase(BaseModel):
    name: str
    description: Optional[str] = None
    group_ids: List[int] = []


class GroupBatch(GroupBatchBase):
    id: Optional[int] = None
    group_count: int = 0
    campaign_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ClientBatchBase(BaseModel):
    name: str
    description: Optional[str] = None
    client_ids: List[int] = []


class ClientBatch(ClientBatchBase):
    id: Optional[int] = None
    client_count: int = 0
    use_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CampaignBase(BaseModel):
    name: str
    campaign_type: str
    product_id: Optional[int] = None
    group_id: Optional[int] = None
    batch_ids: Optional[List[int]] = None
    client_id: Optional[int] = None
    client_ids: Optional[List[int]] = None
    my_group_link: Optional[str] = None
    scheduled_time: Optional[str] = None
    rePost: bool = False
    repeatPost: bool = False
    frequency: Optional[str] = None
    repeat_day: Optional[int] = None
    repeat_time: Optional[str] = None
    target_scope: str = "single"
    auto_product: bool = False
    batch_size: int = 0
    duration_minutes: int = 60
    capture_replies: bool = False
    capture_dwell_seconds: int = 30

    @field_validator("capture_dwell_seconds")
    @classmethod
    def _capture_dwell(cls, value: int) -> int:
        number = int(value or 0)
        if number < 0:
            return 0
        if number > 600:
            return 600
        return number


class Campaign(CampaignBase):
    id: Optional[int] = None
    status: str = "isScheduledFor"
    posts_sent: int = 0
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None


class CampaignInput(CampaignBase):
    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("name is required")
        return text

    @field_validator("my_group_link", mode="before")
    @classmethod
    def _link(cls, value):
        return _clean_url(value, "link")


class ScheduleBase(BaseModel):
    campaign_id: int
    start_time: str
    end_time: str


class Schedule(ScheduleBase):
    id: Optional[int] = None
    status: str = "active"
    campaign_name: Optional[str] = None
    frequency: Optional[str] = None
    repeatPost: bool = False


class LogEntry(BaseModel):
    id: Optional[int] = None
    level: str = "info"
    message: str
    source: str = "bot"
    created_at: Optional[datetime] = None


# ── Live Dataflow payload (/live/db, versioned) ───────────────────────────
class LiveDbHealth(BaseModel):
    id: str
    label: str
    status: str  # idle | ok | warning | critical
    percent: float = 0.0  # rough relative load 0..100, drives bar width
    detail: str = ""


class LiveDbFlow(BaseModel):
    id: str
    label: str
    sent_per_min: float = 0.0
    failed_1m: int = 0
    total: int = 0
    processed: int = 0
    status: str = "idle"  # idle | running | completed | failed | stopped


class LiveDbStepFailure(BaseModel):
    step: str
    count: int


class LiveDbEvent(BaseModel):
    id: Optional[int] = None
    level: str = "info"
    event_type: str = "progress"
    message: str
    created_at: Optional[str] = None


class LiveDbRun(BaseModel):
    active: bool = False
    run_id: Optional[int] = None
    campaign_name: Optional[str] = None
    status: Optional[str] = None
    phase: Optional[str] = None
    total: int = 0
    processed: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    remaining: int = 0
    preview: int = 0


class LiveDbPayload(BaseModel):
    """Versioned payload served by GET /live/db (v=1).

    Shape: { v, ts, pools[], flows[], events[], runs{}, steps[], db{},
    scheduler_tick_seconds } — unknown keys are ignored by older/newer
    clients; missing optional keys default instead of throwing.
    """

    v: int = 1
    ts: str
    pools: List[LiveDbHealth]
    flows: List[LiveDbFlow]
    events: List[LiveDbEvent]
    runs: LiveDbRun
    steps: List[LiveDbStepFailure] = []
    db: Dict[str, Any] = {}
    scheduler_tick_seconds: int = 5


FEEDBACK_TYPES = ("bug", "improvement", "other")
FEEDBACK_SEVERITIES = ("low", "medium", "high", "critical")
FEEDBACK_STATUSES = ("new", "triaged", "done")


class FeedbackBase(BaseModel):
    type: str = "bug"
    severity: str = "medium"
    title: str
    description: str
    steps: Optional[str] = None
    expected: Optional[str] = None
    actual: Optional[str] = None
    screenshots: List[str] = []

    @field_validator("screenshots")
    @classmethod
    def _screenshots(cls, value):
        out = []
        for item in value or []:
            text = str(item or "").strip()
            if not text:
                continue
            if not text.startswith("/uploads/"):
                raise ValueError("screenshot must be an uploaded file path")
            out.append(text)
        return out

    @field_validator("type")
    @classmethod
    def _type(cls, value: str) -> str:
        text = str(value or "").strip().lower()
        if text not in FEEDBACK_TYPES:
            raise ValueError(f"type must be one of {', '.join(FEEDBACK_TYPES)}")
        return text

    @field_validator("severity")
    @classmethod
    def _severity(cls, value: str) -> str:
        text = str(value or "").strip().lower()
        if text not in FEEDBACK_SEVERITIES:
            raise ValueError(f"severity must be one of {', '.join(FEEDBACK_SEVERITIES)}")
        return text

    @field_validator("title", "description")
    @classmethod
    def _required(cls, value: str, info) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{info.field_name} is required")
        return text


class Feedback(FeedbackBase):
    id: Optional[int] = None
    status: str = "new"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class FeedbackInput(FeedbackBase):
    pass


class FeedbackUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def _status(cls, value: str) -> str:
        text = str(value or "").strip().lower()
        if text not in FEEDBACK_STATUSES:
            raise ValueError(f"status must be one of {', '.join(FEEDBACK_STATUSES)}")
        return text
