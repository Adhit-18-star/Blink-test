

from fastapi import FastAPI, Request, Form
from fastapi import File, UploadFile
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import base64
import uuid
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
print("DATABASE_URL =", DATABASE_URL)

def get_conn():
     return psycopg2.connect(DATABASE_URL)

app = FastAPI()

os.makedirs("uploads", exist_ok=True)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(SessionMiddleware, secret_key="blink-secret-key")

templates = Jinja2Templates(directory="templates")


 # ---------------- DB ----------------
def init_db():
     conn = get_conn()
     cur = conn.cursor()

     # Users
     cur.execute("""
         CREATE TABLE IF NOT EXISTS users(
             id SERIAL PRIMARY KEY,
             username TEXT UNIQUE,
             password TEXT
         )
     """)

     # Friends
     cur.execute("""
         CREATE TABLE IF NOT EXISTS friends(
             id SERIAL PRIMARY KEY,
             sender TEXT,
             receiver TEXT,
             status TEXT
         )
     """)

     # Messages
     cur.execute("""
         CREATE TABLE IF NOT EXISTS messages(
             id SERIAL PRIMARY KEY,
             sender TEXT,
             receiver TEXT,
             message TEXT,
             timestamp TEXT        )
     """)

     # Safe migration
     try:
         cur.execute("""
             ALTER TABLE messages
             ADD COLUMN IF NOT EXISTS timestamp TEXT
         """)
     except Exception as e:
         print("Timestamp column check:", e)
         conn.rollback()
        
     try:
         cur.execute("""
             ALTER TABLE detective_cases
             ADD COLUMN IF NOT EXISTS required_xp INTEGER DEFAULT 0
         """)
     except:
         conn.rollback()

     # Detective Cases
     cur.execute("""
         CREATE TABLE IF NOT EXISTS detective_cases(
             id SERIAL PRIMARY KEY,
             title TEXT,
             story TEXT,
             clues TEXT,
             suspects TEXT,
             culprit TEXT,
             difficulty TEXT,
             xp INTEGER,
             required_xp INTEGER DEFAULT 0
         )
     """)

     # Detective Progress
     cur.execute("""
         CREATE TABLE IF NOT EXISTS detective_progress(
             id SERIAL PRIMARY KEY,
             username TEXT,
             case_id INTEGER,
             xp INTEGER
         )
     """)

     conn.commit()
     cur.close()
     conn.close()


init_db()

 # ---------------- HOME ----------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
     return RedirectResponse("/login", status_code=303)


 # ---------------- LOGIN ----------------
@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
     return templates.TemplateResponse(
         "register.html",
         {"request": request}
     )
    
@app.post("/register")
def register(
     username: str = Form(...),
     password: str = Form(...)
 ):
     conn = get_conn()
     cur = conn.cursor()

     try:
         cur.execute(
             "INSERT INTO users(username,password) VALUES(%s,%s)",
             (username, password)
         )
         conn.commit()
         conn.close()
         return RedirectResponse("/login", status_code=303)

     except:
         conn.close()
         return HTMLResponse("Username already exists")

@app.get("/login")
def login_page(request: Request):
     return templates.TemplateResponse(
         request=request,
        name="login.html"
     )

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
     conn = get_conn()
     cur = conn.cursor()

     cur.execute(
         "SELECT username FROM users WHERE username=%s AND password=%s",
         (username, password)
     )

     user = cur.fetchone()
     conn.close()

     if not user:
         return HTMLResponse("Invalid login ❌", status_code=401)

     request.session["username"] = username

     return RedirectResponse("/dashboard", status_code=303)


 # ---------------- DASHBOARD ----------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
     username = request.session.get("username")
     if not username:
         return RedirectResponse("/login")

     return templates.TemplateResponse("dashboard.html", {
         "request": request,
         "username": username
     })


 # ---------------- USERS ----------------
@app.get("/users", response_class=HTMLResponse)
def users(request: Request):
     username = request.session.get("username")
     if not username:
         return RedirectResponse("/login")

     conn = get_conn()
     cur = conn.cursor()

     cur.execute("SELECT username FROM users WHERE username != %s", (username,))
     users = cur.fetchall()
     conn.close()

     return templates.TemplateResponse("users.html", {
         "request": request,
         "users": users
     })


 # ---------------- FRIEND REQUEST ----------------
@app.post("/send-request")
def send_request(request: Request, receiver: str = Form(...)):
     sender = request.session.get("username")
     if not sender:
         return RedirectResponse("/login")

     conn = get_conn()
     cur = conn.cursor()

     cur.execute(
         "INSERT INTO friends(sender, receiver, status) VALUES (%s, %s, 'pending')",
         (sender, receiver)
     )

     conn.commit()
     conn.close()

     return RedirectResponse("/users", status_code=303)


 # ---------------- REQUESTS ----------------
@app.get("/requests", response_class=HTMLResponse)
def requests_page(request: Request):
     username = request.session.get("username")
     if not username:
         return RedirectResponse("/login")

     conn = get_conn()
     cur = conn.cursor()

     cur.execute(
         "SELECT id, sender FROM friends WHERE receiver=%s AND status='pending'",
         (username,)
     )

     requests = cur.fetchall()
     conn.close()

     return templates.TemplateResponse("requests.html", {
         "request": request,
         "requests": requests
     })


 # ---------------- ACCEPT REQUEST ----------------
@app.post("/accept-request")
def accept(request_id: int = Form(...)):
     conn = get_conn()
     cur = conn.cursor()

     cur.execute("UPDATE friends SET status='accepted' WHERE id=%s", (request_id,))

     conn.commit()
     conn.close()

     return RedirectResponse("/requests", status_code=303)


 # ---------------- CHAT LIST ----------------
@app.get("/friends", response_class=HTMLResponse)
def friends(request: Request):
    username = request.session.get("username")
    if not username:
         return RedirectResponse("/login", status_code=303)

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
         SELECT sender, receiver
         FROM friends
         WHERE status='accepted'
         AND (sender=%s OR receiver=%s)
     """, (username, username))

    data = cur.fetchall()
    conn.close()

    friend_set = set()

    for s, r in data:
         friend_set.add(r if s == username else s)

    return templates.TemplateResponse("friends.html", {
         "request": request,
         "friends": list(friend_set)
     })


 # ---------------- CHAT PAGE ----------------
@app.get("/chat/{friend}", response_class=HTMLResponse)
def chat(request: Request, friend: str):
    username= request.session.get("username")
    if not username:
         return RedirectResponse("/login")
    
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, sender, message, timestamp
        FROM messages
        WHERE (sender=%s AND receiver=%s)
        OR (sender=%s AND receiver=%s)
        ORDER BY id 
    """, (username, friend, friend, username))

    messages = cur.fetchall()
    conn.close()

    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "messages": messages,
            "friend": friend,
            "username": username
        }
    )


# ---------------- SEND MESSAGE ----------------
@app.post("/chat/{friend}")
def send_message(request: Request, friend: str, message: str = Form(...)):
    username = request.session.get("username")
    if not username:
        return RedirectResponse("/login")

    conn = get_conn()
    cur = conn.cursor()

    current_time = datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).strftime("%I:%M %p")

    cur.execute(
        "INSERT INTO messages(sender, receiver, message, timestamp) VALUES (%s, %s, %s, %s)",
        (username, friend, message, current_time)
    )

    conn.commit()
    conn.close()

    return RedirectResponse(f"/chat/{friend}", status_code=303)


# ---------------- WHO AM I ----------------
@app.get("/whoami")
def whoami(request: Request):
    return {"username": request.session.get("username")}

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    username = request.session.get("username")

    if not username:
        return RedirectResponse("/login", status_code=303)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "username": username
    })

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)

@app.post("/upload/{friend}")
def upload_image(friend: str, file: UploadFile = File(...), request: Request = None):
    username = request.session.get("username")

    if not username:
        return {"error": "not logged in"}

    file_path = f"/uploads/{file.filename}"

    with open(file_path, "wb") as buffer:
        buffer.write(file.file.read())

    conn = get_conn()
    cur = conn.cursor()

    current_time = datetime.now().strftime("%I:%M %p")

    cur.execute(
        "INSERT INTO messages(sender, receiver, message, timestamp) VALUES (%s, %s, %s, %s)",
        (username, friend, file_path, current_time)
    )

    conn.commit()
    conn.close()

    return {"message": "image sent"}

@app.get("/delete-message/{msg_id}/{friend}")
def delete_message(msg_id: int, friend: str):

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM messages WHERE id=%s",
        (msg_id,)
    )

    conn.commit()
    conn.close()

    return RedirectResponse(
        f"/chat/{friend}",
        status_code=303
    )

@app.get("/camera", response_class=HTMLResponse)
def camera(request: Request):
    return templates.TemplateResponse("camera.html", {"request": request})



@app.post("/camera-upload/{friend}")
async def camera_upload(friend: str, request: Request):
    data = await request.json()

    image_data = data["image"]

    # remove base64 header
    image_data = image_data.split(",")[1]

    filename = f"{uuid.uuid4()}.png"

    save_path = f"uploads/{filename}"
    db_path = f"/uploads/{filename}"

    with open(save_path, "wb") as f:
        f.write(base64.b64decode(image_data))

    conn = get_conn()
    cur = conn.cursor()

    username = request.session.get("username")

    current_time = datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).strftime("%I:%M %p")

    cur.execute(
        "INSERT INTO messages(sender, receiver, message, timestamp) VALUES (%s, %s, %s, %s)",
        (username, friend, db_path, current_time)
    )

    conn.commit()
    conn.close()

    return {"message": "sent"}

@app.get("/camera/{friend}", response_class=HTMLResponse)
def camera(request: Request, friend: str):
    return templates.TemplateResponse("camera.html", {
        "request": request,
        "friend": friend
    })
    
@app.get("/filters/{friend}", response_class=HTMLResponse)
def filters(request: Request, friend: str):
    return templates.TemplateResponse(
        "filter.html",
        {
            "request": request,
            "friend": friend
        }
    )
    
@app.get("/test")
def test():
    return HTMLResponse("<h1>Test works</h1>")

@app.get("/test-template")
def test_template(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )

@app.get("/test-users")
def test_users():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users")
    data = cur.fetchall()

    conn.close()

    return {"users": data}

@app.get("/count-users")
def count_users():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]

    conn.close()

    return {"count": count}


@app.get("/debug-users-page")
def debug_users_page(request: Request):
    username = request.session.get("username")

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "SELECT username FROM users WHERE username != %s",
        (username,)
    )

    data = cur.fetchall()

    conn.close()

    return {
        "logged_in_as": username,
        "users": data
    }
    
@app.get("/search-users")
def search_users(request: Request, q: str = ""):
    username = request.session.get("username")

    if not username:
        return {"error": "not logged in"}

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            u.username,
            CASE
                WHEN f.id IS NOT NULL THEN 'sent'
                ELSE 'none'
            END AS request_status
        FROM users u
        LEFT JOIN friends f
            ON f.sender = %s
            AND f.receiver = u.username
        WHERE u.username ILIKE %s
        AND u.username != %s
        ORDER BY u.username
    """, (username, f"%{q}%", username))

    users = cur.fetchall()

    cur.close()
    conn.close()

    return {"users": users}

@app.get("/test-users")
def test_users():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT username FROM users")

    users = cur.fetchall()

    cur.close()
    conn.close()

    return users
    
@app.get("/detective/clues", response_class=HTMLResponse)
def detective_clues(request: Request):

    clues = [
        "Muddy shoe prints near the sports room",
        "Watchman has keys",
        "Arjun practiced on muddy ground",
        "Coach left school at 5 PM"
    ]

    return templates.TemplateResponse(
        "clues.html",
        {
            "request": request,
            "clues": clues
        }
    )
    
@app.get("/detective/suspects", response_class=HTMLResponse)
def detective_suspects(request: Request):

    return templates.TemplateResponse(
        "suspects.html",
        {
            "request": request
        }
    )
    
@app.post("/detective/result", response_class=HTMLResponse)
def detective_result(
    request: Request,
    suspect: str = Form(...)
):

    correct = "Arjun"

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "suspect": suspect,
            "correct": correct,
            "won": suspect == correct
        }
    )
    
@app.get("/add-all-cases")
def add_all_cases():

    cases = [

    (
    "The Missing Trophy",
    "The school trophy disappeared one day before Sports Day.",
    "A muddy footprint was found near the trophy room|Rahul was seen near the room after school|The room was locked with a key",
    "Rahul|Watchman Suresh|Coach Ravi",
    "Rahul",
    "Easy",
    10
    ),

    (
    "The Lost Science Project",
    "A science project vanished before the exhibition.",
    "A bottle of glue was left behind|A student saw Priya carrying a large box|The project was found in Class 8B",
    "Priya|Amit|Teacher Meera",
    "Priya",
    "Easy",
    10
    ),

    (
    "The Vanished Homework",
    "A notebook containing homework disappeared.",
    "The notebook was last seen on a desk|Rohan sat at that desk after lunch|The notebook was found in Rohan's bag",
    "Rohan|Karan|Sneha",
    "Rohan",
    "Easy",
    10
    ),

    (
    "The Missing Library Book",
    "A popular library book disappeared.",
    "The last borrower was Anjali|The book was found under Anjali's desk|No one else borrowed it",
    "Anjali|Librarian|Ritesh",
    "Anjali",
    "Easy",
    10
    ),

    (
    "The Stolen Football",
    "The football used for practice went missing.",
    "Vikas was playing with it last|The ball was found in Vikas's garage|No one else took it home",
    "Vikas|Coach Ravi|Arjun",
    "Vikas",
    "Easy",
    10
    ),

    (
    "The Broken Classroom Clock",
    "The classroom clock was broken during recess.",
    "A cricket ball hit the wall|Sameer was playing cricket nearby|The ball belonged to Sameer",
    "Sameer|Rohit|Watchman",
    "Sameer",
    "Easy",
    10
    ),

    (
    "The Missing Exam Papers",
    "A stack of practice exam papers disappeared.",
    "Neha wanted extra copies|Papers were found in Neha's locker|No signs of forced entry",
    "Neha|Teacher Meera|Aman",
    "Neha",
    "Easy",
    10
    ),

    (
    "The Lost Art Painting",
    "A painting prepared for the art competition vanished.",
    "Paint stains were found on Kunal's hands|Kunal carried a drawing tube home|The painting was inside the tube",
    "Kunal|Riya|Art Teacher",
    "Kunal",
    "Easy",
    10
    ),

    (
    "The Mystery of the Empty Lunch Box",
    "A student's lunch disappeared.",
    "Food crumbs were found near Ajay's seat|Ajay skipped bringing lunch that day|Ajay admitted eating it",
    "Ajay|Rohan|Sneha",
    "Ajay",
    "Easy",
    10
    ),

    (
    "The Missing Cricket Cap",
    "The captain's cricket cap disappeared before the match.",
    "The cap was last seen in the locker room|Manav was changing there after practice|The cap was found in Manav's bag",
    "Manav|Coach Ravi|Watchman Suresh",
    "Manav",
    "Easy",
    10
    )

    ]

    conn = get_conn()
    cur = conn.cursor()

    for case in cases:
        cur.execute("""
            INSERT INTO detective_cases
            (title, story, clues, suspects, culprit, difficulty, xp)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, case)

    conn.commit()
    conn.close()

    return {"message": "All cases added"}
    
@app.get("/detective", response_class=HTMLResponse)
def detective(request: Request):

    username = request.session.get("username")

    conn = get_conn()
    cur = conn.cursor()

    # User XP
    cur.execute("""
        SELECT COALESCE(SUM(xp),0)
        FROM detective_progress
        WHERE username=%s
    """, (username,))

    user_xp = cur.fetchone()[0]

    # Cases
    cur.execute("""
        SELECT id, title, difficulty, xp, required_xp
        FROM detective_cases
        ORDER BY id
    """)

    cases = cur.fetchall()

    conn.close()

    return templates.TemplateResponse(
        "detective_cases.html",
        {
            "request": request,
            "cases": cases,
            "user_xp": user_xp   # 👈 THIS MUST EXIST
        }
    )
    
@app.get("/case/{case_id}", response_class=HTMLResponse)
def play_case(request: Request, case_id: int):

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, title, story, clues, suspects
        FROM detective_cases
        WHERE id=%s
    """, (case_id,))

    case = cur.fetchone()

    conn.close()

    if not case:
        return HTMLResponse("Case not found", status_code=404)

    suspects = case[4].split("|")
    clues = case[3].split("|")

    return templates.TemplateResponse(
        "case.html",
        {
            "request": request,
            "case": case,
            "clues": clues,
            "suspects": suspects
        }
    )
    
@app.post("/accuse/{case_id}", response_class=HTMLResponse)
def accuse(
    request: Request,
    case_id: int,
    suspect: str = Form(...)
):

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT culprit, xp
        FROM detective_cases
        WHERE id=%s
    """, (case_id,))

    data = cur.fetchone()

    conn.close()

    culprit = data[0]
    xp = data[1]

    won = suspect == culprit
    
    if won:
        username = request.session.get("username")

        conn = get_conn()
        cur = conn.cursor()

        cur.execute("""
            SELECT id
            FROM detective_progress
            WHERE username=%s
            AND case_id=%s
        """, (username, case_id))

        already_done = cur.fetchone()

        if not already_done:

            cur.execute("""
                INSERT INTO detective_progress
                (username, case_id, xp)
                VALUES (%s,%s,%s)
            """, (username, case_id, xp))

            conn.commit()

        conn.close()

    return templates.TemplateResponse(
        "case_result.html",
        {
            "request": request,
            "won": won,
            "suspect": suspect,
            "culprit": culprit,
            "xp": xp
        }
    )


@app.get("/reset-detective-xp")
def reset_detective_xp(request: Request):

    username = request.session.get("username")

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM detective_progress
        WHERE username=%s
    """, (username,))

    conn.commit()
    conn.close()

    return {"message": "XP reset"}

@app.get("/detective-profile", response_class=HTMLResponse)
def detective_profile(request: Request):

    username = request.session.get("username")

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT COALESCE(SUM(xp),0)
        FROM detective_progress
        WHERE username=%s
    """, (username,))

    xp = cur.fetchone()[0]

    conn.close()

    if xp >= 1000:
        level = "Legend Detective"
        next_xp = 1000
    elif xp >= 600:
        level = "Master Detective"
        next_xp = 1000
    elif xp >= 350:
        level = "Expert Detective"
        next_xp = 600
    elif xp >= 200:
        level = "Senior Detective"
        next_xp = 350
    elif xp >= 100:
        level = "School Detective"
        next_xp = 200
    elif xp >= 50:
        level = "Junior Detective"
        next_xp = 100
    else:
        level = "Rookie Detective"
        next_xp = 50

    progress = min(int((xp / next_xp) * 100), 100)

    return templates.TemplateResponse(
        "detective_profile.html",
        {
            "request": request,
            "username": username,
            "xp": xp,
            "level": level,
            "progress": progress,
            "next_xp": next_xp
        }
    )
    
@app.get("/setup-case-xp")
def setup_case_xp():

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE detective_cases
        SET required_xp = (id - 1) * 10
    """)

    conn.commit()
    conn.close()

    return {"message":"XP requirements added"}