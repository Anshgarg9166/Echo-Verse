# server/utils.py
from functools import wraps
from flask import request, jsonify
from models import get_token

def require_bearer(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "missing_token"}), 401
        token = auth.split(" ", 1)[1]
        t = get_token(token)
        if not t:
            return jsonify({"error": "invalid_token"}), 401
        # attach user_id to request context
        request.user_id = t["user_id"]
        return f(*args, **kwargs)
    return decorated
