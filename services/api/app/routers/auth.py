from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.schemas.auth_schema import LoginRequest, RegisterRequest, TokenResponse, UserPublic
from app.schemas.common import Envelope
from app.services.auth_service import authenticate_user, register_user
from app.utils.responses import success


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=Envelope[UserPublic],
    summary="Register a new user",
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    user = register_user(db=db, username=payload.username, email=payload.email, password=payload.password)
    return success(UserPublic.model_validate(user).model_dump(), "User registered")


@router.post(
    "/login",
    response_model=Envelope[TokenResponse],
    summary="Login and receive a JWT access token",
)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict:
    token = authenticate_user(db=db, username=payload.username, password=payload.password)
    return success(TokenResponse(access_token=token).model_dump(), "Login success")


@router.get(
    "/me",
    response_model=Envelope[UserPublic],
    summary="Get current user profile",
)
def me(user=Depends(get_current_user)) -> dict:
    return success(UserPublic.model_validate(user).model_dump())

