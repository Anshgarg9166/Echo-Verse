# server/oauth.py
import time
import secrets
import hashlib
import base64
from models import (
    save_authorization_code,
    get_authorization_code,
    delete_authorization_code,
    save_token,
    get_oauth_client,
)

# Generate a secure random authorization code
def generate_authorization_code():
    return secrets.token_urlsafe(32)

# Create and persist an authorization code document (JSON-serializable)
def create_code_doc(client_id, redirect_uri, user_id, code_challenge, code_challenge_method, scope=""):
    code = generate_authorization_code()
    doc = {
        "code": code,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "user_id": str(user_id),
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "scope": scope,
        "created_at": int(time.time())
    }
    # Persist to DB via models.save_authorization_code
    save_authorization_code(doc)
    return doc

# Verify PKCE code_verifier against stored code_doc
def verify_pkce(code_doc, code_verifier):
    if not code_doc:
        return False
    method = code_doc.get("code_challenge_method", "S256")
    stored_challenge = code_doc.get("code_challenge")
    if method == "S256":
        # compute base64url(SHA256(code_verifier)) without padding
        sha256 = hashlib.sha256(code_verifier.encode()).digest()
        calc = base64.urlsafe_b64encode(sha256).rstrip(b"=").decode()
        return calc == stored_challenge
    else:
        # 'plain' method (not recommended) — compare directly
        return code_verifier == stored_challenge

# Issue a simple access token and persist it (returns a JSON-safe dict)
def issue_token(client_id, user_id, scope=""):
    access_token = secrets.token_urlsafe(48)
    token_doc = {
        "access_token": access_token,
        "client_id": client_id,
        "user_id": str(user_id),
        "scope": scope,
        "token_type": "Bearer",
        "expires_in": 3600,
        "created_at": int(time.time())
    }
    # persist token document
    save_token(token_doc)
    # return only serializable fields
    return {
        "access_token": token_doc["access_token"],
        "token_type": token_doc["token_type"],
        "expires_in": token_doc["expires_in"],
        "scope": token_doc["scope"]
    }
