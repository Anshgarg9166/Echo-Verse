# server/app.py
from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
from config import SECRET_KEY, BASE_URL, ACCESS_TOKEN_EXPIRES
# models: import only what we use
from models import (
    create_user,
    verify_user,
    create_oauth_client,
    get_oauth_client,
    save_authorization_code,
    get_authorization_code,
    delete_authorization_code,
)
from oauth import create_code_doc, verify_pkce, issue_token
from utils import require_bearer
import secrets
import json
from chunk_stream import _flush_buffer, _BUFFERS_META, _BUFFERS, _LOCK, _transcribe_file


app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
CORS(app)


from stt import stt_bp
app.register_blueprint(stt_bp, url_prefix="/api")

from process import process_bp
app.register_blueprint(process_bp, url_prefix="/api")

from chunk_stream import chunk_bp
app.register_blueprint(chunk_bp, url_prefix="/api")


# ---------------------
# Register
# ---------------------
@app.route("/register", methods=["POST"])
def register():
    data = request.json or {}
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    if not name or not email or not password:
        return jsonify({"error": "invalid_input"}), 400
    u = create_user(name, email, password)
    if not u:
        return jsonify({"error": "user_exists"}), 400
    return jsonify({"success": True, "user_id": u["_id"]}), 201

# ---------------------
# Simple login for dev/testing (not OAuth)
# ---------------------
@app.route("/login", methods=["POST"])
def login():
    data = request.json or {}
    email = data.get("email")
    password = data.get("password")
    u = verify_user(email, password)
    if not u:
        return jsonify({"error": "invalid_credentials"}), 401
    # For quick testing, issue a token-like object via issue_token
    token = issue_token("echoverse-mobile-client", str(u["_id"]), scope="")
    return jsonify(token)

# ---------------------
# Authorization endpoint (Authorization Code + PKCE)
# Clients (mobile) will open this URL in a system browser (or webview)
# GET /authorize?response_type=code&client_id=...&redirect_uri=...&scope=...&state=...&code_challenge=...&code_challenge_method=S256
# ---------------------
@app.route("/authorize", methods=["GET", "POST"])
def authorize():
    if request.method == "GET":
        # Validate parameters and show a simple consent/login page (for demo we show auto-accept by query)
        client_id = request.args.get("client_id")
        redirect_uri = request.args.get("redirect_uri")
        state = request.args.get("state")
        code_challenge = request.args.get("code_challenge")
        code_challenge_method = request.args.get("code_challenge_method", "S256")
        # Basic validation
        client = get_oauth_client(client_id)
        if not client:
            return "Invalid client", 400
        if redirect_uri not in client.get("redirect_uris", []):
            return "Invalid redirect URI", 400
        # In real app: render login/consent form. For dev/demo, we accept a user_id query to simulate login.
        # Example: /authorize?...&user_id=<user_id>
        user_id = request.args.get("user_id")
        if not user_id:
            # instruct developer to pass user_id for demo convenience
            return f"Missing user_id in demo mode. Append &user_id=USER_ID to auto-authorize. client_id={client_id}", 400

        # Create authorization code
        code_doc = create_code_doc(client_id, redirect_uri, user_id, code_challenge, code_challenge_method)
        # Redirect back with code & state
        redirect_to = f"{redirect_uri}?code={code_doc['code']}"
        if state:
            redirect_to += f"&state={state}"
        return redirect(redirect_to)

    # POST: not used in this simplified demo. Real server should accept login credentials via POST.
    return "Allow only GET in demo", 405

# ---------------------
# Token endpoint: exchange code + code_verifier for tokens
# POST /token with body: grant_type=authorization_code&code=...&redirect_uri=...&client_id=...&code_verifier=...
# ---------------------
@app.route("/token", methods=["POST"])
def token():
    # Support form-encoded body
    grant_type = request.form.get("grant_type")
    if grant_type != "authorization_code":
        return jsonify({"error": "unsupported_grant_type"}), 400

    code = request.form.get("code")
    redirect_uri = request.form.get("redirect_uri")
    client_id = request.form.get("client_id")
    code_verifier = request.form.get("code_verifier")

    if not (code and redirect_uri and client_id and code_verifier):
        return jsonify({"error": "invalid_request"}), 400

    cd = get_authorization_code(code)
    if not cd:
        return jsonify({"error": "invalid_grant"}), 400

    # Validate client_id/redirect_uri
    if cd["client_id"] != client_id or cd["redirect_uri"] != redirect_uri:
        return jsonify({"error": "invalid_grant"}), 400

    # Verify PKCE
    if not verify_pkce(cd, code_verifier):
        return jsonify({"error": "invalid_grant", "error_description": "PKCE verification failed"}), 400

    # Issue token
    token_doc = issue_token(client_id, cd["user_id"], scope=cd.get("scope", ""))
    # Clean up auth code
    delete_authorization_code(code)
    return jsonify({
        "access_token": token_doc["access_token"],
        "token_type": "Bearer",
        "expires_in": token_doc["expires_in"],
        "scope": token_doc["scope"]
    })

# ---------------------
# Protected userinfo example
# ---------------------
@app.route("/userinfo")
@require_bearer
def userinfo():
    # request.user_id is set by decorator
    return jsonify({"user_id": request.user_id})

def init_oauth_client():
    """
    One-time initialization: create a default OAuth client for local development if it doesn't exist.
    We run this in main() to be compatible with Flask 3.x (no before_first_request).
    """
    client_id = "echoverse-mobile-client"
    if not get_oauth_client(client_id):
        # Add the redirect URIs you will use in development (expo / deep link / local web)
        create_oauth_client(
            client_id,
            ["echoverse://oauth", "http://localhost:19006/--/*"],
            name="EchoVerse mobile client"
        )
        print("Created default client:", client_id)

# if __name__ == "__main__":
#     # Run initialization (one-time) before starting the server
#     try:
#         init_oauth_client()
#     except Exception as e:
#         print("Warning: init_oauth_client failed:", e)
#     app.run(host="0.0.0.0", port=8000, debug=True)
if __name__ == "__main__":
    try:
        # single-process dev server (no reloader) — stable on Windows
        app.run(host="0.0.0.0", port=8000, debug=True, use_reloader=False)
    except KeyboardInterrupt:
        print("Server stopped by user")

@app.route("/api/flush", methods=["POST"])
def flush_manual():
    from chunk_stream import _flush_buffer, _transcribe_file, _BUFFERS_META, _LOCK
    import os

    data = request.get_json() or {}
    session_id = data.get("session_id")

    if not session_id:
        return jsonify({"error": "missing_session_id"}), 400

    file_path = _flush_buffer(session_id)
    if not file_path:
        return jsonify({"status": "empty"})

    result = _transcribe_file(file_path)
    try:
        os.remove(file_path)
    except:
        pass

    # remove session meta
    with _LOCK:
        _BUFFERS_META.pop(session_id, None)

    return jsonify(result)
