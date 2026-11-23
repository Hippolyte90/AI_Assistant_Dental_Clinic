"""Account routes: sign up, sign in, sign out."""

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services.auth import (
    COOKIE_NAME,
    SESSION_SECONDS,
    AccountError,
    AccountExists,
    AccountLimitReached,
    User,
    create_token,
    verify_token,
)

router = APIRouter(prefix="/api/auth")


class LoginRequest(BaseModel):
    """Sign-in form."""

    email: str
    password: str


class RegisterRequest(LoginRequest):
    """Sign-up form."""

    name: str


def client_id(request: Request) -> str:
    """Visitor address; behind the tunnel, Cloudflare sets this header."""
    forwarded = request.headers.get("cf-connecting-ip")
    return forwarded or (request.client.host if request.client else "unknown")


def current_user(request: Request) -> User | None:
    """The signed-in user, if any."""
    user_id = verify_token(request.app.state.auth_secret, request.cookies.get(COOKIE_NAME))
    return request.app.state.users.get(user_id) if user_id else None


def _failure(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error_code": code, "message": message})


def _public(user: User) -> dict:
    return {"name": user.name, "email": user.email}


def _signed_in(request: Request, user: User, status: int = 200) -> JSONResponse:
    response = JSONResponse(
        status_code=status, content={"authenticated": True, "user": _public(user)}
    )
    response.set_cookie(
        COOKIE_NAME,
        create_token(request.app.state.auth_secret, user.id),
        max_age=SESSION_SECONDS,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        path="/",
    )
    return response


@router.get("/status")
def status(request: Request) -> dict:
    """Whether this browser is signed in."""
    if not request.app.state.workflow.settings.auth_required:
        return {"required": False, "authenticated": True, "user": None}
    user = current_user(request)
    return {
        "required": True,
        "authenticated": user is not None,
        "user": _public(user) if user else None,
    }


@router.post("/register")
def register(body: RegisterRequest, request: Request) -> Response:
    """Create an account and sign in."""
    limiter = request.app.state.register_limiter
    client = client_id(request)
    if not limiter.allowed(client):
        return _failure(429, "too_many_attempts", "Too many new accounts. Please try again later.")
    try:
        user = request.app.state.users.create(body.name, body.email, body.password)
    except AccountExists as exc:
        return _failure(409, "account_exists", str(exc))
    except AccountLimitReached as exc:
        return _failure(403, "accounts_closed", str(exc))
    except AccountError as exc:
        return _failure(400, "invalid_account", str(exc))
    limiter.record(client)
    return _signed_in(request, user, status=201)


@router.post("/login")
def login(body: LoginRequest, request: Request) -> Response:
    """Check the email and password and open a session."""
    limiter = request.app.state.login_limiter
    client = client_id(request)
    if not limiter.allowed(client):
        return _failure(
            429, "too_many_attempts", "Too many attempts. Please try again in 15 minutes."
        )
    user = request.app.state.users.authenticate(body.email, body.password)
    if user is None:
        limiter.record(client)
        return _failure(401, "wrong_credentials", "Incorrect email or password.")
    limiter.reset(client)
    return _signed_in(request, user)


@router.post("/logout")
def logout() -> Response:
    """Close the session."""
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response
