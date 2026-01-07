import os
import requests
import bcrypt
from flask import Flask, request, jsonify
from flask_cors import CORS
from bson import ObjectId
from datetime import datetime, timezone
from werkzeug.utils import secure_filename

# تأكد من وجود ملف ai_service.py وملف db.py في نفس المجلد
from ai_service import AIService
from db import users_col, db 

# تعريف الكولكشنز
posts_col = db["posts"]
bookings_col = db["bookings"]
messages_col = db["messages"]
transactions_col = db["transactions"]
# كولكشن التقييمات الجديد
ratings_col = db["ratings"]

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ======================
# CONFIGURATION & WHEREBY SETUP
# ======================
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# مفتاح Whereby
WHEREBY_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2FjY291bnRzLmFwcGVhci5pbiIsImF1ZCI6Imh0dHBzOi8vYXBpLmFwcGVhci5pbi92MSIsImV4cCI6OTAwNzE5OTI1NDc0MDk5MSwiaWF0IjoxNzY3NDUxNzE0LCJvcmdhbml6YXRpb25JZCI6MzMyMTI2LCJqdGkiOiIyYzNmMTZlYS1iM2YxLTRiOGQtYTJkMC03ODhhNzM5ZGNiODUifQ.nkaUDATWwDiKj_LVCkqHYS-eDq43WcsQN1NMxE-jpfw"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/get-meeting-link/<booking_id>")
def get_meeting_link(booking_id):
    user_role = request.args.get("role")
    booking = bookings_col.find_one({"_id": ObjectId(booking_id)})
    if not booking or "roomUrl" not in booking: return jsonify({"error": "Not ready"}), 404
    url = booking["hostRoomUrl"] if user_role == "teacher" else booking["roomUrl"]
    # تم إضافة باراميترز لتقليل واجهة المستخدم
    return jsonify({"url": f"{url}?embed&chat=on&info=off&floatSelf=on"})

# ======================
# 2. AUTH & USER ROUTES
# ======================
@app.route("/")
def home(): return jsonify({"status": "SkillSwap backend is running"})

@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.json
    if users_col.find_one({"email": data["email"]}): return jsonify({"error": "Email already exists"}), 400
    hashed_pw = bcrypt.hashpw(data["password"].encode("utf-8"), bcrypt.gensalt())
    roles = ["learner"]
    if data.get("teach_skills"): roles.append("teacher")
    user = {
        "fullName": data["full_name"], "email": data["email"], "passwordHash": hashed_pw,
        "headline": "", "bio": "", "profilePicture": "https://i.pravatar.cc/150",
        "roles": roles, "skillTags": data.get("teach_skills", []), "creditBalance": 10,
        "ratingAvg": 0.0, "totalReviews": 0, "createdAt": datetime.now(timezone.utc)
    }
    result = users_col.insert_one(user)
    return jsonify({"message": "Account created", "userId": str(result.inserted_id)}), 201

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    user = users_col.find_one({"email": data.get("email")})
    if not user: return jsonify({"error": "Invalid email or password"}), 401
    
    stored_pw = user["passwordHash"]
    if isinstance(stored_pw, str): stored_pw = stored_pw.encode('utf-8')
    
    if not bcrypt.checkpw(data["password"].encode("utf-8"), stored_pw):
        return jsonify({"error": "Invalid email or password"}), 401
        
    return jsonify({
        "message": "Login successful", "userId": str(user["_id"]),
        "fullName": user["fullName"], "profilePicture": user.get("profilePicture", "https://i.pravatar.cc/150"),
        "roles": user.get("roles", ["learner"])
    }), 200

@app.route("/api/users/<user_id>")
def get_user(user_id):
    try:
        user = users_col.find_one({"_id": ObjectId(user_id)}, {"passwordHash": 0})
        if not user: return jsonify({"error": "User not found"}), 404
        user["_id"] = str(user["_id"])
        return jsonify(user)
    except: return jsonify({"error": "Invalid User ID"}), 400

@app.route("/api/users/<user_id>", methods=["PUT"])
def update_user(user_id):
    data = request.json
    update_data = {}
    if "fullName" in data and data["fullName"]: update_data["fullName"] = data["fullName"]
    if "headline" in data: update_data["headline"] = data["headline"]
    if "bio" in data: update_data["bio"] = data["bio"]
    if "skills" in data: update_data["skillTags"] = [s.strip() for s in data["skills"].split(",") if s.strip()]
    if "learnSkills" in data: update_data["learningSkills"] = data["learnSkills"]

    if update_data:
        users_col.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})
        return jsonify({"message": "Updated successfully"}), 200
    return jsonify({"message": "No changes"}), 200

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
        return jsonify({"message": "Uploaded", "url": url}), 200
    return jsonify({"error": "File type error"}), 400

# ======================
# 3. SEARCH & SKILLS
# ======================
@app.route("/api/search")
def search_users():
    skill_query = request.args.get("skill", "").strip()
    if not skill_query:
        users = list(users_col.find({"roles": "teacher"}, {"passwordHash": 0}))
    else:
        regex_pattern = {"$regex": skill_query, "$options": "i"}
        users = list(users_col.find({"skillTags": regex_pattern, "roles": "teacher"}, {"passwordHash": 0}))
    
    for u in users: u["_id"] = str(u["_id"])
    return jsonify(users)

@app.route("/api/teachers/all")
def get_all_teachers():
    teachers = list(users_col.find({"roles": "teacher"}, {"passwordHash": 0}))
    for t in teachers: t["_id"] = str(t["_id"])
    return jsonify(teachers)

@app.route("/api/teach-skill", methods=["POST"])
def publish_skill():
    data = request.json
    user_id = data.get("userId")
    new_skill = data.get("skillName")

    if not user_id or not new_skill:
        return jsonify({"error": "Missing info"}), 400

    users_col.update_one(
        {"_id": ObjectId(user_id)},
        {
            "$addToSet": {"skillTags": new_skill, "roles": "teacher"} 
        }
    )
    return jsonify({"message": "Skill published successfully!"}), 200

# ======================
# 4. COMMUNITY & POSTS
# ======================
@app.route("/api/posts", methods=["GET"])
def get_posts():
    topic = request.args.get("topic")
    query = {}
    if topic and topic != "All Topics": query["topic"] = topic
    posts = list(posts_col.find(query).sort("_id", -1))
    for p in posts: p["_id"] = str(p["_id"])
    return jsonify(posts)

@app.route("/api/posts", methods=["POST"])
def create_post():
    data = request.json
    user = users_col.find_one({"_id": ObjectId(data["userId"])})
    new_post = {
        "userId": data["userId"], "authorName": user["fullName"],
        "authorPic": user.get("profilePicture", "https://i.pravatar.cc/150"),
        "topic": data["topic"], "title": data["title"], "content": data["content"],
        "likes": 0, "comments": [], "createdAt": datetime.now(timezone.utc).isoformat()
    }
    result = posts_col.insert_one(new_post)
    new_post["_id"] = str(result.inserted_id)
    return jsonify(new_post), 201

@app.route("/api/posts/<post_id>/like", methods=["PUT"])
def like_post(post_id):
    posts_col.update_one({"_id": ObjectId(post_id)}, {"$inc": {"likes": 1}})
    return jsonify({"message": "Liked"}), 200

@app.route("/api/posts/<post_id>/comment", methods=["POST"])
def add_comment(post_id):
    data = request.json
    comment = {"authorName": data["authorName"], "text": data["text"], "createdAt": datetime.now(timezone.utc).isoformat()}
    posts_col.update_one({"_id": ObjectId(post_id)}, {"$push": {"comments": comment}})
    return jsonify({"message": "Comment added", "comment": comment}), 200

# ======================
# 5. WALLET & TRANSACTIONS
# ======================
@app.route("/api/wallet/update", methods=["POST"])
def update_wallet():
    data = request.json
    user_id, amount = data.get("userId"), data.get("amount")
    users_col.update_one({"_id": ObjectId(user_id)}, {"$inc": {"creditBalance": int(amount)}})
    tx_type = "deposit" if int(amount) > 0 else "payment"
    transactions_col.insert_one({
        "user": ObjectId(user_id), "type": tx_type, "amount": int(amount),
        "description": data.get("description", "Balance Update"), "date": datetime.now(timezone.utc).strftime("%b %d, %Y")
    })
    return jsonify({"message": "Transaction successful"}), 200

@app.route("/api/wallet/transfer", methods=["POST"])
def transfer_credits():
    data = request.json
    sender_id, recipient_email = data.get("senderId"), data.get("recipientEmail")
    amount = int(data.get("amount"))
    sender = users_col.find_one({"_id": ObjectId(sender_id)})
    recipient = users_col.find_one({"email": recipient_email})
    if not recipient or sender["creditBalance"] < amount: return jsonify({"error": "Check balance/recipient"}), 400
    users_col.update_one({"_id": ObjectId(sender_id)}, {"$inc": {"creditBalance": -amount}})
    users_col.update_one({"_id": recipient["_id"]}, {"$inc": {"creditBalance": amount}})
    return jsonify({"message": "Transfer successful"}), 200

@app.route("/api/wallet/history/<user_id>")
def get_history(user_id):
    transactions = list(db.transactions.find({
        "$or": [{"learnerId": user_id}, {"teacherId": user_id}, {"user": ObjectId(user_id)}]
    }).sort("timestamp", -1))
    
    history = []
    for t in transactions:
        desc = t.get("description", "Transaction")
        date_str = t["timestamp"].strftime("%Y-%m-%d") if isinstance(t.get("timestamp"), datetime) else t.get("date", "N/A")
        
        amt = t.get("amount", 0)
        if t.get("type") == "skill_swap" and str(t.get("learnerId")) == user_id:
            amt = -amt
        
        history.append({
            "description": desc,
            "date": date_str,
            "amount": amt
        })
    return jsonify(history)

# ======================
# 6. MESSAGING SYSTEM
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
    pipeline = [{"$match": {"$or": [{"senderId": user_id}, {"receiverId": user_id}]}}, {"$group": {"_id": None, "ids": {"$addToSet": "$senderId"}, "ids2": {"$addToSet": "$receiverId"}}}]
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

@app.route("/api/messages/mark-read/<user_id>/<contact_id>", methods=["PUT"])
def mark_read(user_id, contact_id):
    messages_col.update_many({"senderId": contact_id, "receiverId": user_id, "read": False}, {"$set": {"read": True}})
    return jsonify({"success": True})

# ======================
# 7. BOOKING & REVIEWS
# ======================
@app.route("/api/bookings", methods=["POST"])
def create_booking():
    data = request.json
    new_booking = {
        "learnerId": data["learnerId"], "teacherId": data["teacherId"],
        "learnerName": data["learnerName"], "teacherName": data["teacherName"],
        "skill": data["skill"], "date": data["date"], "time": data["time"],
        "status": "pending", "createdAt": datetime.now(timezone.utc).isoformat()
    }
    bookings_col.insert_one(new_booking)
    return jsonify({"message": "Booking request sent!"}), 201

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
        
        if not ObjectId.is_valid(booking_id):
            return jsonify({"error": "Invalid ID format"}), 400
        
        booking_oid = ObjectId(booking_id)
        booking = bookings_col.find_one({"_id": booking_oid})
        
        if not booking: 
            return jsonify({"error": "Booking not found"}), 404

        # منطق القبول (Accept)
        if new_status == "confirmed" and booking.get("status") == "pending":
            learner_id_str = booking.get("learnerId")
            teacher_id_str = booking.get("teacherId")

            if not learner_id_str or not teacher_id_str:
                return jsonify({"error": "Missing IDs in booking"}), 400

            learner_oid = ObjectId(learner_id_str)
            teacher_oid = ObjectId(teacher_id_str)

            # التحقق من الرصيد
            learner = users_col.find_one({"_id": learner_oid})
            if not learner: return jsonify({"error": "Learner not found"}), 404
                
            if learner.get("creditBalance", 0) < 1:
                return jsonify({"error": "Student has 0 credits!"}), 400

            # 1. خصم من الطالب
            users_col.update_one({"_id": learner_oid}, {"$inc": {"creditBalance": -1}})
            
            # 2. إضافة للمعلم
            users_col.update_one({"_id": teacher_oid}, {"$inc": {"creditBalance": 1}})
            
            # 3. تسجيل العملية
            transaction_doc = {
                "learnerId": learner_id_str,
                "teacherId": teacher_id_str,
                "user": learner_oid, 
                "amount": 1, 
                "timestamp": datetime.now(timezone.utc), 
                "type": "skill_swap",
                "description": f"Session: {booking.get('skill', 'Unknown')}"
            }
            
            try:
                transactions_col.insert_one(transaction_doc)
            except Exception as e:
                print(f"Transaction Log Error (Ignored): {e}")

        # تحديث الحالة النهائية
        bookings_col.update_one({"_id": booking_oid}, {"$set": {"status": new_status}})
        return jsonify({"message": f"Success! Session is {new_status}"}), 200

    except Exception as e:
        print(f"❌ SERVER ERROR: {e}")
        return jsonify({"error": f"Server Error: {str(e)}"}), 500

@app.route("/api/bookings/<booking_id>/finish", methods=["PUT"])
def finish_booking(booking_id):
    bookings_col.update_one({"_id": ObjectId(booking_id)}, {"$set": {"status": "completed"}})
    return jsonify({"message": "Session finished"}), 200

@app.route("/api/reviews", methods=["POST"])
def submit_review():
    data = request.json
    teacher_id = data.get("teacherId")
    rating = int(data.get("rating"))
    db.reviews.insert_one({"teacherId": teacher_id, "learnerId": data.get("learnerId"), "rating": rating, "comment": data.get("comment"), "createdAt": datetime.now(timezone.utc)})
    all_reviews = list(db.reviews.find({"teacherId": teacher_id}))
    avg_rating = round(sum(r["rating"] for r in all_reviews) / len(all_reviews), 1)
    users_col.update_one({"_id": ObjectId(teacher_id)}, {"$set": {"ratingAvg": avg_rating, "totalReviews": len(all_reviews)}})
    return jsonify({"message": "Review submitted"}), 200

# ======================
# 8. LEADERBOARD & STATS
# ======================
@app.route("/api/leaderboard", methods=["GET"])
def get_leaderboard():
    top_teachers = list(users_col.find(
        {"roles": "teacher"},
        {"fullName": 1, "ratingAvg": 1, "totalReviews": 1, "profilePicture": 1, "skillTags": 1}
    ).sort("ratingAvg", -1).limit(5))
    for t in top_teachers: t["_id"] = str(t["_id"])
    return jsonify(top_teachers), 200

@app.route("/api/admin/stats", methods=["GET"])
def get_admin_stats():
    try:
        total_users = users_col.count_documents({})
        active_sessions_query = {"status": {"$in": ["confirmed", "ready"]}}
        active_sessions_count = db.bookings.count_documents(active_sessions_query)
        
        pipeline = [{"$group": {"_id": None, "total": {"$sum": "$creditBalance"}}}]
        total_credits_res = list(users_col.aggregate(pipeline))
        total_credits = total_credits_res[0]["total"] if total_credits_res else 0
        
        active_sessions_list = list(db.bookings.find(active_sessions_query).sort("createdAt", -1).limit(10))
        for s in active_sessions_list: s["_id"] = str(s["_id"])

        recent_users = list(users_col.find().sort("createdAt", -1).limit(5))
        for u in recent_users:
            u["_id"] = str(u["_id"])
            if "passwordHash" in u: del u["passwordHash"]

        return jsonify({
            "totalUsers": total_users,
            "totalBookings": active_sessions_count,
            "totalPlatformCredits": total_credits,
            "activeSessions": active_sessions_list,
            "recentUsers": recent_users
        }), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/admin/users/<user_id>", methods=["DELETE"])
def delete_user(user_id):
    try:
        users_col.delete_one({"_id": ObjectId(user_id)})
        return jsonify({"message": "User deleted"}), 200
    except: return jsonify({"error": "Error"}), 500

# ======================
# 9. SOCIAL LOGIN
# ======================
@app.route("/api/auth/social-login", methods=["POST"])
def social_login():
    data = request.json
    email = data.get("email")
    user = users_col.find_one({"email": email})

    if not user:
        new_user = {
            "fullName": data.get("name"), "email": email, "profilePicture": data.get("picture"),
            "passwordHash": "SOCIAL_AUTH", "creditBalance": 10, "roles": ["learner"],
            "skillTags": [], "learningSkills": [], "createdAt": datetime.now(timezone.utc)
        }
        result = users_col.insert_one(new_user)
        user_id = str(result.inserted_id)
        credits, roles, pic, name = 10, ["learner"], data.get("picture"), data.get("name")
    else:
        user_id = str(user["_id"])
        credits, roles, pic, name = user.get("creditBalance", 0), user.get("roles", ["learner"]), user.get("profilePicture"), user.get("fullName")

    return jsonify({"status": "success", "userId": user_id, "fullName": name, "profilePicture": pic, "creditBalance": credits, "roles": roles})

# ======================
# 10. AI ROUTES
# ======================
@app.route("/api/ai/matches/<user_id>")
def get_ai_matches(user_id):
    try:
        user = users_col.find_one({"_id": ObjectId(user_id)})
        interests = user.get("learningSkills", []) + user.get("skillTags", [])
        
        teachers = list(users_col.find({"roles": "teacher", "_id": {"$ne": ObjectId(user_id)}}))
        
        teachers_data = [{
            "id": str(t["_id"]), 
            "name": t["fullName"], 
            "skills": t.get("skillTags", []),
            "headline": t.get("headline", "Mentor")
        } for t in teachers]
        
        recommendations = AIService.get_smart_matches(interests, teachers_data)
        
        if not recommendations and teachers_data:
            t = teachers_data[0]
            recommendations = [{
                "id": t["id"], "name": t["name"], "role": "Mentor", 
                "match_percentage": "85%", "reason": "Recommended based on community popularity."
            }]

        return jsonify({"recommendations": recommendations})
        
    except Exception as e:
        print(f"Match Route Error: {e}")
        return jsonify({"recommendations": []})

@app.route("/api/ai/generate-bio", methods=["POST"])
def ai_generate_bio():
    data = request.json
    name = data.get("name")
    skills = data.get("skills")
    headline = data.get("headline", "")

    if not name or not skills:
        return jsonify({"error": "Missing data"}), 400

    try:
        new_bio = AIService.generate_bio(name, skills, headline)
        return jsonify({"bio": new_bio})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

<<<<<<< Updated upstream
# ======================
# 11. NEW RATING SYSTEM (Corrected for MongoDB)
# ======================
@app.route('/api/save-rating', methods=['POST'])
def save_rating():
    try:
        # استقبال البيانات
        data = request.get_json()

        # 1. استخراج البيانات (حسب الـ Schema المطلوبة)
        rating = data.get('rating')
        reviewer = data.get('reviewer')     # المستخدم الذي يقيم
        target_user = data.get('targetUser') # المستخدم الذي يتم تقييمه

        # 2. التحقق من صحة البيانات
        if not rating or not reviewer or not target_user:
            return jsonify({'success': False, 'message': 'بيانات ناقصة: rating, reviewer, targetUser مطلوبين'}), 400

        # التأكد أن التقييم رقم صحيح بين 1 و 5
        try:
            rating = int(rating)
            if not (1 <= rating <= 5):
                raise ValueError
        except ValueError:
            return jsonify({'success': False, 'message': 'التقييم يجب أن يكون رقم بين 1 و 5'}), 400

        # 3. تجهيز الوثيقة للحفظ في MongoDB
        rating_doc = {
            "rating": rating,
            "reviewer": reviewer,
            "targetUser": target_user,
            "createdAt": datetime.now(timezone.utc)
        }

        # 4. الحفظ في الكولكشن (Ratings)
        # سيتم استخدام ratings_col المعرف في الأعلى
        ratings_col.insert_one(rating_doc)

        # 5. (اختياري) تحديث متوسط تقييم المعلم في جدول المستخدمين
        # لضمان ظهور النجوم الجديدة في البروفايل مباشرة
        all_ratings = list(ratings_col.find({"targetUser": target_user}))
        if all_ratings:
            avg_rating = round(sum(r["rating"] for r in all_ratings) / len(all_ratings), 1)
            users_col.update_one(
                {"_id": ObjectId(target_user)}, 
                {"$set": {"ratingAvg": avg_rating, "totalReviews": len(all_ratings)}}
            )

        return jsonify({'success': True, 'message': 'تم حفظ التقييم بنجاح'}), 200

    except Exception as e:
        print(f"Error saving rating: {e}")
        return jsonify({'success': False, 'message': 'حدث خطأ في السيرفر'}), 500
=======

# هذا المسار هو الذي تبحث عنه صفحة survey1.html و survey2.html
@app.route("/api/users/<user_id>/update-profile", methods=["POST"])
def update_profile_survey(user_id):
    data = request.json
    update_data = {}

    # معالجة مهارات التعليم (survey1)
    if "teachSkills" in data:
        update_data["skillTags"] = data["teachSkills"]
        update_data["roles"] = ["learner", "teacher"] # تفعيل دور المعلم فوراً

    # معالجة مهارات التعلم (survey2)
    if "learnSkills" in data:
        update_data["learningSkills"] = data["learnSkills"]

    # معالجة العنوان الوظيفي
    if "headline" in data:
        update_data["headline"] = data["headline"]

    if update_data:
        users_col.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})
        return jsonify({"message": "Profile updated successfully"}), 200
    
    return jsonify({"error": "No data provided"}), 400

>>>>>>> Stashed changes

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)