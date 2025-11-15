# server/add_redirect_uri.py
from pymongo import MongoClient
from config import MONGO_URI

client = MongoClient(MONGO_URI)
db = client.get_default_database()
oauth_clients = db.oauth_clients

client_id = "echoverse-mobile-client"
new_uri = "http://localhost:3000/callback"

res = oauth_clients.update_one(
    {"client_id": client_id},
    {"$addToSet": {"redirect_uris": new_uri}}
)

if res.matched_count == 0:
    print("Client not found. You may need to create the client first.")
else:
    print("Updated client:", client_id)
    doc = oauth_clients.find_one({"client_id": client_id})
    print("redirect_uris:", doc.get("redirect_uris"))
