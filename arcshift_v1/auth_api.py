"""Local test-account routes, separate from the unchanged fixture read API."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from .auth import AuthService, CSRF_COOKIE, SESSION_COOKIE, normalize_test_email
from .schemas import SyntheticModel


router = APIRouter(prefix="/api/v1/auth", tags=["local-test-accounts"])


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: Annotated[str, Field(min_length=3, max_length=254, strict=True)]

    @field_validator("email")
    @classmethod
    def test_email_only(cls, value):
        return normalize_test_email(value)


class Credentials(EmailRequest):
    password: SecretStr

    @field_validator("password")
    @classmethod
    def password_length(cls, value):
        if not 15 <= len(value.get_secret_value()) <= 128:
            raise ValueError("Password must contain 15 to 128 characters")
        return value


class VerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: SecretStr

    @field_validator("token")
    @classmethod
    def token_length(cls, value):
        if not 32 <= len(value.get_secret_value()) <= 128:
            raise ValueError("Invalid verification token")
        return value


class PasswordResetConfirmation(VerificationRequest):
    password: Annotated[SecretStr, Field(min_length=15, max_length=128)]


class AuthView(SyntheticModel):
    auth_contract_version: Literal["v1-local-auth.1"] = "v1-local-auth.1"
    production_ready: Literal[False] = False


class OutboxRequestAccepted(AuthView):
    status: Literal["accepted"] = "accepted"
    delivery_mode: Literal["local_outbox_only"] = "local_outbox_only"


class CurrentUser(AuthView):
    user_id: str
    email: str
    verified: Literal[True] = True


class AuthCapabilities(AuthView):
    local_registration_and_verification: Literal[True] = True
    local_login_logout_sessions: Literal[True] = True
    real_mail_delivery: Literal[False] = False
    password_recovery_implemented: Literal[True] = True
    verification_resend_implemented: Literal[False] = False
    allowed_email_domain_suffix: Literal[".test"] = ".test"


def service(request: Request) -> AuthService:
    auth = getattr(request.app.state, "auth_service", None)
    if auth is None:
        raise HTTPException(503, detail={"code": "local_auth_unavailable", "synthetic": True})
    return auth


def same_origin(request: Request):
    expected = str(request.base_url).rstrip("/")
    if request.headers.get("origin") != expected:
        raise HTTPException(403, detail={"code": "same_origin_required", "synthetic": True})


def peer(request):
    return "unknown" if request.client is None else request.client.host


@router.get("/capabilities", response_model=AuthCapabilities)
def capabilities(auth: AuthService = Depends(service)):
    return AuthCapabilities()


@router.post("/register", status_code=202, response_model=OutboxRequestAccepted, dependencies=[Depends(same_origin)])
def register(data: Credentials, request: Request, auth: AuthService = Depends(service)):
    auth.register(data.email, data.password.get_secret_value(), peer(request))
    return OutboxRequestAccepted()


@router.post("/password-reset/request", status_code=202, response_model=OutboxRequestAccepted, dependencies=[Depends(same_origin)])
def request_password_reset(data: EmailRequest, request: Request, auth: AuthService = Depends(service)):
    auth.request_password_reset(data.email, peer(request))
    return OutboxRequestAccepted()


@router.post("/password-reset/confirm", status_code=204, dependencies=[Depends(same_origin)])
def confirm_password_reset(data: PasswordResetConfirmation, request: Request, auth: AuthService = Depends(service)):
    auth.reset_password(data.token.get_secret_value(), data.password.get_secret_value(), peer(request))
    return Response(status_code=204)


@router.post("/verify-email", status_code=204, dependencies=[Depends(same_origin)])
def verify(data: VerificationRequest, request: Request, auth: AuthService = Depends(service)):
    auth.verify_email(data.token.get_secret_value(), peer(request))
    return Response(status_code=204)


@router.post("/login", status_code=204, dependencies=[Depends(same_origin)])
def login(data: Credentials, request: Request, auth: AuthService = Depends(service)):
    session, csrf = auth.login(data.email, data.password.get_secret_value(), peer(request), request.cookies.get(SESSION_COOKIE))
    response = Response(status_code=204)
    response.set_cookie(SESSION_COOKIE, session, max_age=auth.policy.session_seconds, path="/", httponly=True, secure=False, samesite="strict")
    response.set_cookie(CSRF_COOKIE, csrf, max_age=auth.policy.session_seconds, path="/", httponly=False, secure=False, samesite="strict")
    return response


@router.get("/me", response_model=CurrentUser)
def me(request: Request, auth: AuthService = Depends(service)):
    identity = auth.authenticate(request.cookies.get(SESSION_COOKIE))
    return CurrentUser(user_id=identity.user_id, email=identity.email)


@router.post("/logout", status_code=204, dependencies=[Depends(same_origin)])
def logout(request: Request, auth: AuthService = Depends(service)):
    auth.logout(request.cookies.get(SESSION_COOKIE), request.headers.get("x-csrf-token"))
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=False, samesite="strict")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=False, samesite="strict")
    return response
