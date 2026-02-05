"""
Firebase Authentication Configuration

Initializes Firebase Admin SDK and provides token verification.
Supports both Firebase and Google IAP authentication methods.
"""

import os
import json
import logging
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Firebase Admin SDK - imported lazily to avoid hard dependency
_firebase_app = None
_firebase_initialized = False

# Dev-only fallback for session signing (never used in production)
_DEV_SESSION_SECRET = "dev-secret-change-in-production"


def _get_session_secret() -> str:
    """Get session signing secret. Fails closed in production if missing."""
    secret = os.environ.get("SESSION_SECRET")
    if secret:
        return secret
    if os.environ.get("ENV") == "production":
        raise RuntimeError("SESSION_SECRET must be set in production — refusing to use dev fallback")
    return _DEV_SESSION_SECRET


def _get_firebase_credentials():
    """
    Get Firebase credentials from environment.

    Supports:
    1. GOOGLE_APPLICATION_CREDENTIALS env var (path to JSON file)
    2. FIREBASE_SERVICE_ACCOUNT_JSON env var (JSON string)
    3. Default application credentials (Cloud Run)
    """
    # Option 1: JSON string in env var
    service_account_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if service_account_json:
        try:
            from firebase_admin import credentials
            cred_dict = json.loads(service_account_json)
            return credentials.Certificate(cred_dict)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse FIREBASE_SERVICE_ACCOUNT_JSON: {e}")
            return None

    # Option 2: Path to JSON file
    cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path and os.path.exists(cred_path):
        try:
            from firebase_admin import credentials
            return credentials.Certificate(cred_path)
        except Exception as e:
            logger.error(f"Failed to load credentials from {cred_path}: {e}")
            return None

    # Option 3: Application default credentials (Cloud Run/GCE)
    try:
        from firebase_admin import credentials
        return credentials.ApplicationDefault()
    except Exception:
        return None


def init_firebase() -> bool:
    """
    Initialize Firebase Admin SDK.

    Returns True if successful, False otherwise.
    Safe to call multiple times - will skip if already initialized.
    """
    global _firebase_app, _firebase_initialized

    if _firebase_initialized:
        return _firebase_app is not None

    try:
        import firebase_admin
        from firebase_admin import auth as firebase_auth

        # Check if already initialized
        try:
            _firebase_app = firebase_admin.get_app()
            _firebase_initialized = True
            logger.info("Firebase already initialized")
            return True
        except ValueError:
            pass  # Not initialized yet

        # Get credentials
        cred = _get_firebase_credentials()

        # Get project ID from env or credentials
        project_id = os.environ.get("FIREBASE_PROJECT_ID")

        options = {}
        if project_id:
            options["projectId"] = project_id

        if cred:
            _firebase_app = firebase_admin.initialize_app(cred, options)
        else:
            # Try without explicit credentials (uses ADC)
            _firebase_app = firebase_admin.initialize_app(options=options if options else None)

        _firebase_initialized = True
        logger.info(f"Firebase initialized successfully (project: {project_id or 'default'})")
        return True

    except ImportError:
        logger.warning("firebase-admin not installed. Firebase auth disabled.")
        _firebase_initialized = True
        return False
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        _firebase_initialized = True
        return False


def verify_firebase_token(token: str) -> Optional[dict]:
    """
    Verify a Firebase ID token.

    Args:
        token: Firebase ID token from client

    Returns:
        Decoded token claims if valid, None otherwise.
        Claims include: uid, email, name, etc.
    """
    if not _firebase_initialized:
        init_firebase()

    if _firebase_app is None:
        logger.warning("Firebase not available for token verification")
        return None

    try:
        from firebase_admin import auth as firebase_auth

        # Verify the token
        decoded_token = firebase_auth.verify_id_token(token)

        return {
            "user_id": decoded_token.get("uid"),
            "email": decoded_token.get("email"),
            "email_verified": decoded_token.get("email_verified", False),
            "display_name": decoded_token.get("name"),
            "picture": decoded_token.get("picture"),
            "auth_time": decoded_token.get("auth_time"),
            "iat": decoded_token.get("iat"),
            "exp": decoded_token.get("exp"),
            "provider_id": decoded_token.get("firebase", {}).get("sign_in_provider"),
        }

    except Exception as e:
        logger.warning(f"Firebase token verification failed: {e}")
        return None


def verify_iap_token(token: str) -> Optional[dict]:
    """
    Verify a Google Identity-Aware Proxy (IAP) JWT.

    IAP tokens come in the X-Goog-IAP-JWT-Assertion header.

    Args:
        token: IAP JWT assertion

    Returns:
        Decoded token claims if valid, None otherwise.
    """
    try:
        from google.auth import jwt as google_jwt
        from google.auth.transport import requests

        # Expected audience for IAP
        expected_audience = os.environ.get("IAP_EXPECTED_AUDIENCE")

        if not expected_audience:
            logger.warning("IAP_EXPECTED_AUDIENCE not set, skipping IAP verification")
            return None

        # Verify and decode the token
        request = requests.Request()
        claims = google_jwt.decode(token, request=request, audience=expected_audience)

        return {
            "user_id": claims.get("sub"),
            "email": claims.get("email"),
            "display_name": claims.get("email", "").split("@")[0],
            "iat": claims.get("iat"),
            "exp": claims.get("exp"),
            "provider_id": "google_iap",
        }

    except ImportError:
        logger.warning("google-auth not installed. IAP verification unavailable.")
        return None
    except Exception as e:
        logger.warning(f"IAP token verification failed: {e}")
        return None


def create_session_token(user_id: str, email: str, expires_in_hours: int = 24) -> str:
    """
    Create a signed session token for cookie-based auth.

    Uses HMAC-SHA256 with a secret key from environment.

    Args:
        user_id: User ID to encode
        email: User email to encode
        expires_in_hours: Token validity period

    Returns:
        Base64-encoded signed token
    """
    import hmac
    import hashlib
    import base64
    from datetime import timedelta

    secret = _get_session_secret()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=expires_in_hours)

    # Create payload
    payload = f"{user_id}:{email}:{int(now.timestamp())}:{int(expires.timestamp())}"

    # Sign with HMAC
    signature = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()

    # Combine and encode
    token = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(token.encode()).decode()


def verify_session_token(token: str) -> Optional[dict]:
    """
    Verify a session token created by create_session_token.

    Args:
        token: Base64-encoded session token

    Returns:
        Decoded claims if valid and not expired, None otherwise.
    """
    import hmac
    import hashlib
    import base64

    secret = _get_session_secret()

    try:
        # Decode
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        parts = decoded.split(":")

        if len(parts) != 5:
            return None

        user_id, email, issued_at, expires_at, signature = parts

        # Verify signature
        payload = f"{user_id}:{email}:{issued_at}:{expires_at}"
        expected_signature = hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_signature):
            logger.warning("Session token signature mismatch")
            return None

        # Check expiration
        now = datetime.now(timezone.utc).timestamp()
        if now > int(expires_at):
            logger.debug("Session token expired")
            return None

        return {
            "user_id": user_id,
            "email": email,
            "iat": int(issued_at),
            "exp": int(expires_at),
            "provider_id": "session",
        }

    except Exception as e:
        logger.warning(f"Session token verification failed: {e}")
        return None
