from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, examples=["admin"])
    email: EmailStr = Field(examples=["admin@example.com"])
    password: str = Field(min_length=8, max_length=128, examples=["P@ssw0rd123"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, examples=["admin"])
    password: str = Field(min_length=1, max_length=128, examples=["P@ssw0rd123"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserPublic(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime

    class Config:
        from_attributes = True

