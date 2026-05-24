from pydantic import BaseModel, Field, field_validator
from typing import Optional


class TextAnalysisRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)

    @field_validator("text")
    @classmethod
    def text_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be blank")
        return v


class TextAnalysisResponse(BaseModel):
    prob: float
    latency_ms: float
    analytics: dict


class PlatformRequest(BaseModel):
    username: str = ""
    handle: str = ""
    identifier: str = ""
    instance: str = Field(default="mastodon.social", max_length=253)
    password: str = ""
    client_id: str = ""
    client_secret: str = ""
    channel_url: str = ""
    video_url: str = ""
    profile_url: str = ""
    api_key: str = ""
    months: int = Field(default=3, ge=1, le=6)
    min_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    n_show: int = Field(default=20, gt=0, le=500)
    transcribe_videos: bool = True
    transcript_limit: int = Field(default=3, ge=0, le=3)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=8, description="Minimum 8 characters")
    role: str = "student"
    dob: Optional[str] = None
    parent_email: Optional[str] = None
    referred_by: Optional[str] = None


class UserResponse(BaseModel):
    email: str
    name: str
    role: str
    role_type: str
    referral_code: str


# ── Group schemas ──────────────────────────────────────────────────────────────

class CreateGroupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)
    member_ids: list[str] = Field(default_factory=list, description="Initial members to add")


class UpdateGroupRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)


class AddMemberRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    role: str = Field(default="member", pattern="^(admin|member)$")


class GroupMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)


class GroupMemberResponse(BaseModel):
    id: str
    user_id: str
    name: str
    email: str
    role: str
    joined_at: str


class GroupResponse(BaseModel):
    id: str
    name: str
    description: str
    avatar_url: str
    created_by: str
    is_active: bool
    member_count: int
    created_at: str
    updated_at: str


class GroupDetailResponse(BaseModel):
    id: str
    name: str
    description: str
    avatar_url: str
    created_by: str
    is_active: bool
    members: list[GroupMemberResponse]
    created_at: str
    updated_at: str


class GroupMessageResponse(BaseModel):
    id: str
    group_id: str
    sender_id: str
    sender_name: str
    message: str
    created_at: str


# ── Notification preference schemas ────────────────────────────────────────────

NOTIFICATION_TYPES = {
    "message", "group_message", "alert", "referral",
    "broadcast", "consent", "approval", "system",
}


class NotificationPreferenceResponse(BaseModel):
    type: str
    enabled: bool
    muted_groups: list[str]


class UpdateNotificationPreferenceRequest(BaseModel):
    enabled: bool | None = None
    muted_groups: list[str] | None = None


class MuteGroupRequest(BaseModel):
    group_id: str = Field(..., min_length=1)
    muted: bool
