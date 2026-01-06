from pymongo import MongoClient

# Fixed: Added tlsAllowInvalidCertificates=true to bypass SSL issues in development
MONGO_URI = "mongodb+srv://skillswap:skillswap%5F1234@m0.sbp4a7w.mongodb.net/?retryWrites=true&w=majority&tlsAllowInvalidCertificates=true"

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    print(" MongoDB connected successfully!")
except Exception as e:
    print(f" MongoDB connection failed: {e}")
    raise

db = client["skillswap"]

users_col = db["users"]
skills_col = db["skills"]
sessions_col = db["sessions"]
transactions_col = db["transactions"]
notifications_col = db["notifications"]
messages_col = db["messages"]
reports_col = db["reports"]
reviews_col = db["reviews"]
categories_col = db["categories"]