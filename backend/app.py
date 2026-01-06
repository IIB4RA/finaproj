import os
import requests
import bcrypt
from flask import Flask, request, jsonify
from flask_cors import CORS
from bson import ObjectId
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
from ai_service import AIService

# ======================
# DATABASE SETUP
# ======================
from db import users_col, db, sessions_col

posts_col = db["posts"]
bookings_col = db["bookings"]
messages_col = db["messages"]
transactions_col = db["transactions"]

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ======================
# CONFIGURATION & WHEREBY SETUP
# ======================
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

WHEREBY_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2FjY291bnRzLmFwcGVhci5pbiIsImF1ZCI6Imh0dHBzOi8vYXBpLmFwcGVhci5pbi92MSIsImV4cCI6OTAwNzE5OTI1NDc0MDk5MSwiaWF0IjoxNzY3NDUxNzE0LCJvcmdhbml6YXRpb25JZCI6MzMyMTI2LCJqdGkiOiIyYzNmMTZlYS1iM2YxLTRiOGQtYTJkMC03ODhhNzM5ZGNiODUifQ.nkaUDATWwDiKj_LVCkqHYS-eDq43WcsQN1NMxE-jpfw"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def serialize_doc(doc):
    if not doc: return None
    if isinstance(doc, list): return [serialize_doc(item) for item in doc]
    if isinstance(doc, dict):
        new_doc = {}
        for key, value in doc.items():
            if isinstance(value, ObjectId):
                new_doc[key] = str(value)
            elif isinstance(value, datetime):
                new_doc[key] = value.isoformat()
            else:
                new_doc[key] = value
        return new_doc
    return doc


# ======================
# 1. VIDEO SESSION ROUTES
# ======================
@app.route("/api/create-session/<booking_id>", methods=["POST"])
def create_session(booking_id):
    booking = bookings_col.find_one({"_id": ObjectId(booking_id)})
    if not booking: return jsonify({"error": "Booking not found"}), 404
    if "roomUrl" in booking: return jsonify({"success": True}), 200

    headers = {"Authorization": f"Bearer {WHEREBY_API_KEY}", "Content-Type": "application/json"}
    data = {
        "roomNamePrefix": f"skillswap-{booking_id[:5]}-",
        "endDate": "2026-12-31T23:59:59Z",
        "fields": ["hostRoomUrl"]
    }
    try:
        response = requests.post("https://api.whereby.dev/v1/meetings", headers=headers, json=data)
        if response.status_code == 201:
            res_data = response.json()
            bookings_col.update_one({"_id": ObjectId(booking_id)}, {"$set": {
                "roomUrl": res_data["roomUrl"], "hostRoomUrl": res_data["hostRoomUrl"], "status": "ready"
            }})
            return jsonify({"success": True}), 201
        return jsonify({"error": "Whereby Error"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/get-meeting-link/<booking_id>")
def get_meeting_link(booking_id):
    user_role = request.args.get("role")
    booking = bookings_col.find_one({"_id": ObjectId(booking_id)})
    if not booking or "roomUrl" not in booking: return jsonify({"error": "Not ready"}), 404
    url = booking["hostRoomUrl"] if user_role == "teacher" else booking["roomUrl"]
    return jsonify({"url": f"{url}?embed&chat=on&info=off&floatSelf=on"})


# ======================
# 2. AUTH & USER ROUTES
# ======================
@app.route("/")
def home(): return jsonify({"status": "SkillSwap backend is running"})


@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.json
    if users_col.find_one({"email": data["email"]}): return jsonify({"error": "Email exists"}), 400
    hashed_pw = bcrypt.hashpw(data["password"].encode("utf-8"), bcrypt.gensalt())
    user = {
        "fullName": data["full_name"], "email": data["email"], "passwordHash": hashed_pw,
        "headline": "", "bio": "", "profilePicture": "https://i.pravatar.cc/150",
        "roles": ["learner", "teacher"] if data.get("teach_skills") else ["learner"],
        "skillTags": data.get("teach_skills", []), "creditBalance": 10,
        "ratingAvg": 0.0, "totalReviews": 0, "createdAt": datetime.now(timezone.utc)
    }
    result = users_col.insert_one(user)
    return jsonify({"message": "Account created", "userId": str(result.inserted_id)}), 201


@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    user = users_col.find_one({"email": data.get("email")})
    if not user: return jsonify({"error": "Invalid login"}), 401
    stored_pw = user["passwordHash"]
    if isinstance(stored_pw, str): stored_pw = stored_pw.encode('utf-8')
    if not bcrypt.checkpw(data["password"].encode("utf-8"), stored_pw):
        return jsonify({"error": "Invalid login"}), 401
    return jsonify(
        {"userId": str(user["_id"]), "fullName": user["fullName"], "profilePicture": user.get("profilePicture")}), 200


@app.route("/api/users/<user_id>")
def get_user(user_id):
    try:
        user = users_col.find_one({"_id": ObjectId(user_id)}, {"passwordHash": 0})
        user["_id"] = str(user["_id"])
        return jsonify(user)
    except:
        return jsonify({"error": "Invalid ID"}), 400


@app.route("/api/users/<user_id>", methods=["PUT"])
def update_user(user_id):
    try:
        data = request.json
        update_data = {}

        # تحديث الحقول الأساسية
        if "fullName" in data: update_data["fullName"] = data["fullName"]
        if "headline" in data: update_data["headline"] = data["headline"]
        if "bio" in data: update_data["bio"] = data["bio"]

        # تحويل مهارات التدريس من نص مفصول بفاصلة إلى مصفوفة
        if "skills" in data:
            update_data["skillTags"] = [s.strip() for s in data["skills"].split(",") if s.strip()]

        # تحويل مهارات التعلم من نص مفصول بفاصلة إلى مصفوفة
        if "learnSkills" in data:
            # إذا كانت قادمة كمصفوفة أصلاً من الفرونت آند
            if isinstance(data["learnSkills"], list):
                update_data["learningSkills"] = data["learnSkills"]
            else:  # إذا كانت قادمة كنص
                update_data["learningSkills"] = [s.strip() for s in data["learnSkills"].split(",") if s.strip()]

        if update_data:
            users_col.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})
            return jsonify({"message": "Updated successfully"}), 200

        return jsonify({"message": "No changes detected"}), 200
    except Exception as e:
        print(f"Update Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/users/<user_id>/upload-picture", methods=["POST"])
def upload_file(user_id):
    if 'file' not in request.files: return jsonify({"error": "No file"}), 400
    file = request.files['file']
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_name = f"{user_id}_{int(datetime.now().timestamp())}_{filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
        url = f"http://127.0.0.1:5000/static/uploads/{unique_name}"
        users_col.update_one({"_id": ObjectId(user_id)}, {"$set": {"profilePicture": url}})
        return jsonify({"url": url}), 200
    return jsonify({"error": "Invalid file"}), 400


# ======================
# 3. EXPLORE & SEARCH
# ======================
@app.route("/api/sessions/explore")
def explore_all_sessions():
    query_text = request.args.get("skill", "").strip()
    category_filter = request.args.get("category", "All")
    db_query = {}
    if category_filter != "All": db_query["category"] = category_filter
    if query_text: db_query["skill"] = {"$regex": query_text, "$options": "i"}
    sessions = list(sessions_col.find(db_query).sort("createdAt", -1))
    for s in sessions:
        s["_id"] = str(s["_id"])
        s["skill"] = s.get("skill", "Expertise")
        s["teacherName"] = s.get("teacherName", "Mentor")
        s["teacherPic"] = s.get("teacherPic", "https://i.pravatar.cc/150")
    return jsonify(serialize_doc(sessions))


@app.route("/api/teach-skill", methods=["POST"])
def publish_skill():
    data = request.json
    user = users_col.find_one({"_id": ObjectId(data["userId"])})
    new_session = {
        "learner": data["userId"], "teacher": data["userId"],
        "skill": data["skillName"], "status": "active",
        "teacherName": user["fullName"], "teacherPic": user.get("profilePicture"),
        "category": data.get("category", "Other"), "createdAt": datetime.now(timezone.utc)
    }
    sessions_col.insert_one(new_session)
    users_col.update_one({"_id": ObjectId(data["userId"])},
                         {"$addToSet": {"skillTags": data["skillName"], "roles": "teacher"}})
    return jsonify({"message": "Success"}), 200


# ======================
# 4. MESSAGING & CONTACTS
# ======================
@app.route("/api/messages", methods=["POST"])
def send_message():
    data = request.json
    messages_col.insert_one({
        "senderId": data["senderId"], "receiverId": data["receiverId"],
        "text": data["text"], "timestamp": datetime.now(timezone.utc).isoformat(), "read": False
    })
    return jsonify({"message": "Sent"}), 201


@app.route("/api/messages/<user1>/<user2>")
def get_conversation(user1, user2):
    query = {"$or": [{"senderId": user1, "receiverId": user2}, {"senderId": user2, "receiverId": user1}]}
    messages = list(messages_col.find(query).sort("timestamp", 1))
    for m in messages: m["_id"] = str(m["_id"])
    return jsonify(messages)


@app.route("/api/messages/contacts/<user_id>")
def get_contacts(user_id):
    pipeline = [{"$match": {"$or": [{"senderId": user_id}, {"receiverId": user_id}]}},
                {"$group": {"_id": None, "ids": {"$addToSet": "$senderId"}, "ids2": {"$addToSet": "$receiverId"}}}]
    res = list(messages_col.aggregate(pipeline))
    if not res: return jsonify([])
    contact_ids = set(res[0]["ids"] + res[0]["ids2"])
    contact_ids.discard(user_id)
    contacts = []
    for cid in contact_ids:
        u = users_col.find_one({"_id": ObjectId(cid)}, {"fullName": 1, "profilePicture": 1, "headline": 1})
        if u: u["_id"] = str(u["_id"]); contacts.append(u)
    return jsonify(contacts)


@app.route("/api/messages/unread-count/<user_id>")
def get_unread_count(user_id):
    count = messages_col.count_documents({"receiverId": user_id, "read": False})
    return jsonify({"unreadCount": count})


# ======================
# 5. WALLET & BOOKING
# ======================
@app.route("/api/wallet/update", methods=["POST"])
def update_wallet():
    data = request.json
    users_col.update_one({"_id": ObjectId(data["userId"])}, {"$inc": {"creditBalance": int(data["amount"])}})
    transactions_col.insert_one({
        "user": ObjectId(data["userId"]), "type": "deposit", "amount": int(data["amount"]),
        "description": "Wallet Top-up", "timestamp": datetime.now(timezone.utc)
    })
    return jsonify({"message": "Success"}), 200


@app.route("/api/wallet/history/<user_id>")
def get_history(user_id):
    transactions = list(db.transactions.find(
        {"$or": [{"learnerId": user_id}, {"teacherId": user_id}, {"user": ObjectId(user_id)}]}).sort("timestamp", -1))
    history = []
    for t in transactions:
        desc = t.get("description", "Transaction")
        date_str = t["timestamp"].strftime("%Y-%m-%d") if isinstance(t.get("timestamp"), datetime) else "N/A"
        amt = t.get("amount", 0)
        if t.get("type") == "skill_swap" and str(t.get("learnerId")) == user_id: amt = -amt
        history.append({"description": desc, "date": date_str, "amount": amt})
    return jsonify(history)


@app.route("/api/bookings", methods=["POST"])
def create_booking():
    data = request.json
    data["status"] = "pending"
    data["createdAt"] = datetime.now(timezone.utc).isoformat()
    bookings_col.insert_one(data)
    return jsonify({"message": "Sent"}), 201


@app.route("/api/bookings/user/<user_id>")
def get_user_bookings(user_id):
    query = {"$or": [{"learnerId": user_id}, {"teacherId": user_id}]}
    bookings = list(bookings_col.find(query).sort("date", 1))
    for b in bookings: b["_id"] = str(b["_id"])
    return jsonify(bookings)


@app.route("/api/bookings/<booking_id>/status", methods=["PUT"])
def update_booking_status(booking_id):
    try:
        data = request.json
        new_status = data.get("status")
        booking = bookings_col.find_one({"_id": ObjectId(booking_id)})
        if new_status == "confirmed" and booking.get("status") == "pending":
            learner_oid, teacher_oid = ObjectId(booking["learnerId"]), ObjectId(booking["teacherId"])
            learner = users_col.find_one({"_id": learner_oid})
            if learner.get("creditBalance", 0) < 1: return jsonify({"error": "No credits"}), 400
            users_col.update_one({"_id": learner_oid}, {"$inc": {"creditBalance": -1}})
            users_col.update_one({"_id": teacher_oid}, {"$inc": {"creditBalance": 1}})
            transactions_col.insert_one(
                {"learnerId": str(learner_oid), "teacherId": str(teacher_oid), "user": learner_oid, "amount": 1,
                 "timestamp": datetime.now(timezone.utc), "type": "skill_swap",
                 "description": f"Session: {booking['skill']}"})
        bookings_col.update_one({"_id": ObjectId(booking_id)}, {"$set": {"status": new_status}})
        return jsonify({"message": "Success"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ======================
# 6. AI DOCTOR (FIXED & SMART)
# ======================
@app.route("/api/ai/generate-bio", methods=["POST"])
def ai_generate_bio_final():
    try:
        data = request.json
        user = users_col.find_one({"_id": ObjectId(data.get("userId"))})
        if not user: return jsonify({"error": "Not found"}), 404

        # Extracting the full context for the Brain AI
        name = user.get("fullName")
        headline = user.get("headline", "")
        # Pulling skills as comma-separated strings for better AI processing
        teach_skills = ", ".join(user.get("skillTags", []))
        learn_skills = ", ".join(user.get("learningSkills", []))

        # Call the upgraded intelligent generator
        new_bio = AIService.generate_bio(name, teach_skills, learn_skills, headline)

        # Save results to the database
        users_col.update_one({"_id": user["_id"]}, {"$set": {"bio": new_bio}})
        return jsonify({"bio": new_bio}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ai/matches/<user_id>")
def get_ai_matches(user_id):
    try:
        user = users_col.find_one({"_id": ObjectId(user_id)})
        interests = user.get("learningSkills", []) + user.get("skillTags", [])
        teachers = list(users_col.find({"roles": "teacher", "_id": {"$ne": ObjectId(user_id)}}))
        teachers_data = [{"id": str(t["_id"]), "name": t["fullName"], "skills": t.get("skillTags", []),
                          "headline": t.get("headline", "Mentor")} for t in teachers]
        recommendations = AIService.get_smart_matches(interests, teachers_data)
        return jsonify({"recommendations": recommendations})
    except:
        return jsonify({"recommendations": []})


# ======================
# 7. ADMIN & COMMUNITY (FIXED)
# ======================
@app.route("/api/admin/stats")
def get_admin_stats():
    try:
        # 1. إحصائيات عامة
        total_users = users_col.count_documents({})
        active_sessions_query = {"status": {"$in": ["confirmed", "ready"]}}
        active_sessions_count = db.bookings.count_documents(active_sessions_query)

        # 2. حساب إجمالي الكريدت في المنصة (Economy Strength)
        pipeline = [{"$group": {"_id": None, "total": {"$sum": "$creditBalance"}}}]
        total_credits_res = list(users_col.aggregate(pipeline))
        total_credits = total_credits_res[0]["total"] if total_credits_res else 0

        # 3. جلب آخر 10 جلسات نشطة لعرضها في الجدول
        active_sessions_list = list(db.bookings.find(active_sessions_query).sort("createdAt", -1).limit(10))
        for s in active_sessions_list: s["_id"] = str(s["_id"])

        # 4. جلب آخر 5 مستخدمين مسجلين
        recent_users = list(users_col.find().sort("createdAt", -1).limit(5))
        for u in recent_users:
            u["_id"] = str(u["_id"])
            if "passwordHash" in u: del u["passwordHash"]  # حماية الباسورد

        return jsonify({
            "totalUsers": total_users,
            "totalBookings": active_sessions_count,
            "totalPlatformCredits": total_credits,
            "activeSessions": active_sessions_list,
            "recentUsers": recent_users
        }), 200
    except Exception as e:
        print(f"Admin Stats Error: {e}")
        return jsonify({"error": str(e)}), 500


# إضافة مسار حذف المستخدم المفقود في الباك آند ليعمل الزر في صفحة الأدمن
@app.route("/api/admin/users/<user_id>", methods=["DELETE"])
def delete_user(user_id):
    try:
        users_col.delete_one({"_id": ObjectId(user_id)})
        return jsonify({"message": "User deleted"}), 200
    except:
        return jsonify({"error": "Error deleting user"}), 500


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)