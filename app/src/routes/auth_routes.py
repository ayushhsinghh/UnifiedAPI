import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse, JSONResponse
from authlib.integrations.starlette_client import OAuth, OAuthError

from configs.config import get_config
from src.database.user_repository import UserRepository
from src.auth.tokens import get_password_hash, verify_password, create_access_token, get_current_user

logger = logging.getLogger(__name__)
cfg = get_config()

router = APIRouter(prefix="/auth", tags=["Authentication"])

# ── Google OAuth2 Setup ──────────────────────────────────────────────────
oauth = OAuth()
oauth.register(
    name="google",
    client_id=cfg.GOOGLE_CLIENT_ID,
    client_secret=cfg.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

# ── Password Authentication Routes ───────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(form_data: OAuth2PasswordRequestForm = Depends()) -> Dict[str, Any]:
    """Register a new user with email (username) and password."""
    user_repo = UserRepository()
    
    existing_user = user_repo.get_user_by_email(form_data.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
        
    hashed_password = get_password_hash(form_data.password)
    user = user_repo.create_user(email=form_data.username, hashed_password=hashed_password)
    
    return {"message": "User created successfully", "email": user["email"]}


@router.post("/token")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()) -> Dict[str, Any]:
    """Login with email and password to get a JWT access token."""
    user_repo = UserRepository()
    user = user_repo.get_user_by_email(form_data.username)
    
    if not user or not user.get("hashed_password"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token = create_access_token(data={"sub": user["email"]})
    
    response = JSONResponse(content={"message": "Successfully logged in", "email": user["email"]})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True, # Must be true for samesite=none
        samesite="none",
        domain=".ayush.ltd" if cfg.ENVIRONMENT == "production" else None,
        max_age=cfg.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return response


# ── Google OAuth2 Routes ─────────────────────────────────────────────────

@router.get("/google/login")
async def login_via_google(request: Request):
    """Redirects the user to the Google OAuth2 consent screen."""
    redirect_uri = request.url_for("google_auth_callback")
    return await oauth.google.authorize_redirect(request, str(redirect_uri))


@router.get("/google/callback")
async def google_auth_callback(request: Request):
    """Handles the callback from Google, creates/updates user, and returns a JWT."""
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as error:
        logger.error(f"OAuth Error: {error.error}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials from Google"
        )
        
    user_info = token.get("userinfo")
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not retrieve user info from Google"
        )
        
    email = user_info.get("email")
    google_id = user_info.get("sub")
    name = user_info.get("name")
    picture = user_info.get("picture")

    user_repo = UserRepository()
    user = user_repo.get_user_by_email(email)
    
    if user:
        # Update existing user with Google info if they logged in via Google
        user_repo.update_user_google_id(email, google_id, name, picture)
    else:
        # Create a new user without a password
        user_repo.create_user(email=email, google_id=google_id, name=name, picture=picture)
        
    access_token = create_access_token(data={"sub": email})
    
    # Return a redirect response to the frontend without the token in the URL
    frontend_redirect_url = f"{cfg.FRONTEND_URL}/?email={email}"
    response = RedirectResponse(url=frontend_redirect_url)
    
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="none",
        domain=".ayush.ltd" if cfg.ENVIRONMENT == "production" else None,
        max_age=cfg.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return response


# ── Common Routes ────────────────────────────────────────────────────────

@router.get("/me")
async def get_current_logged_in_user(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Return the profile of the currently logged-in user."""
    # Sanitize the output (don't send password hash back)
    user_data = current_user.copy()
    user_data.pop("hashed_password", None)
    return user_data

@router.post("/logout")
async def logout():
    """Clear the HttpOnly authentication cookie."""
    response = JSONResponse(content={"message": "Logged out successfully"})
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=True,
        samesite="none",
        domain=".ayush.ltd" if cfg.ENVIRONMENT == "production" else None,
    )
    return response