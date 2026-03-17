"""Pydantic models for request/response schemas."""

from typing import Optional
from pydantic import BaseModel


class AuthRequest(BaseModel):
    api_key: str

    class Config:
        json_schema_extra = {"example": {"api_key": "trade-master-key-2024"}}


class AuthResponse(BaseModel):
    token: str
    session_id: str
    expires_in: int
    message: str


class RateLimitInfo(BaseModel):
    limit: int
    remaining: int
    window_seconds: int
    reset_at: int


class AnalysisResponse(BaseModel):
    sector: str
    report: str
    generated_at: str
    cached: bool
    rate_limit: RateLimitInfo
    session_id: str


class SessionInfo(BaseModel):
    id: str
    type: str
    created_at: str
    last_active: str
    ip: str
    requests_made: int = 0
