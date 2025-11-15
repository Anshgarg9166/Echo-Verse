# server/models.py (patch)

from pymongo import MongoClient
from bson.objectid import ObjectId
from config import MONGO_URI
import bcrypt

client = MongoClient(MONGO_URI)
db = client.get_default_database()

users = db.users
oauth_clients = db.oauth_clients
oauth_codes = db.oauth_codes
oauth_tokens = db.oauth_tokens

# helper to convert ObjectId -> str recursively for a doc
def serialize_doc(doc):
    if not doc:
        return doc
    serialized = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            serialized[k] = str(v)
        elif isinstance(v, list):
            serialized[k] = [serialize_doc(x) if isinstance(x, dict) else x for x in v]
        elif isinstance(v, dict):
            serialized[k] = serialize_doc(v)
        else:
            serialized[k] = v
    return serialized

def create_user(name, email, password):
    if users.find_one({"email": email}):
        return None
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    user = {"name": name, "email": email, "password": pw_hash}
    res = users.insert_one(user)
    user["_id"] = str(res.inserted_id)
    # do NOT return password hash to caller
    user.pop("password", None)
    return user

def verify_user(email, password):
    u = users.find_one({"email": email})
    if not u:
        return None
    if bcrypt.checkpw(password.encode(), u["password"]):
        u["_id"] = str(u["_id"])
        u.pop("password", None)
        return u
    return None

def create_oauth_client(client_id, redirect_uris, name="mobile-client"):
    doc = {
        "client_id": client_id,
        "client_name": name,
        "redirect_uris": redirect_uris,
        "token_endpoint_auth_method": "none"
    }
    res = oauth_clients.insert_one(doc)
    doc["_id"] = str(res.inserted_id)
    return doc

def get_oauth_client(client_id):
    doc = oauth_clients.find_one({"client_id": client_id})
    return serialize_doc(doc)

def save_authorization_code(code_doc):
    res = oauth_codes.insert_one(code_doc)
    code_doc["_id"] = str(res.inserted_id)
    return code_doc

def get_authorization_code(code):
    doc = oauth_codes.find_one({"code": code})
    return serialize_doc(doc)

def delete_authorization_code(code):
    oauth_codes.delete_one({"code": code})

def save_token(token_doc):
    res = oauth_tokens.insert_one(token_doc)
    token_doc["_id"] = str(res.inserted_id)
    return token_doc

def get_token(access_token):
    doc = oauth_tokens.find_one({"access_token": access_token})
    return serialize_doc(doc)
