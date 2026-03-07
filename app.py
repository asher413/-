import os
import time
from flask import Flask, request, make_response
import yt_dlp
from urllib.parse import quote

app = Flask(__name__)

# --- הגדרות מערכת ---
ACCESS_MODE = "whitelist"
TARGET_PHONE = "0534133753"
FORBIDDEN_WORDS = ["מילה_אסורה1", "תוכן_רע"]

# --- זיכרון זמני ---
SEARCH_CACHE = {}
CACHE_TIME = 300

# מערכת ניהול סשנים לזיהוי השלב בו נמצא כל מתקשר
CALL_SESSIONS = {}

# --- בדיקת שרת ---
@app.route('/')
def home():
    return "SERVER_OK"

def get_cached_search(query):
    now = time.time()
    if query in SEARCH_CACHE:
        data, timestamp = SEARCH_CACHE[query]
        if now - timestamp < CACHE_TIME:
            return data
    return None

def set_cached_search(query, data):
    SEARCH_CACHE[query] = (data, time.time())

# --- yt-dlp options ---
def get_yt_options(is_search=True):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestaudio/best',
        'user_agent': 'Mozilla/5.0',
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extract_flat': is_search,
        'force_ipv4': True,
        'retries': 5,
        'socket_timeout': 20,
    }
    return opts

def is_filtered(text):
    if not text:
        return False
    return any(word.lower() in str(text).lower() for word in FORBIDDEN_WORDS)

# פונקציית עזר לתשובות ימות המשיח
def make_yemot_response(text):
    print("RESPONSE:", text)
    response = make_response(text + "\n")
    response.headers['Content-Type'] = "text/plain; charset=utf-8"
    return response

@app.route('/youtube', methods=['GET','POST'])
def main_logic():
    phone = request.args.get("ApiPhone", "").strip()
    call_id = request.args.get("ApiCallId", "")

    # ניהול ניתוקים - ניקוי הזיכרון
    if request.args.get("hangup"):
        print("DEBUG: hangup")
        if call_id in CALL_SESSIONS:
            del CALL_SESSIONS[call_id]
        return make_response("")

    print(f"DEBUG phone={phone} args={request.args.to_dict()}")

    is_authorized = True
    if ACCESS_MODE == "whitelist" and phone != TARGET_PHONE:
        is_authorized = False
    elif ACCESS_MODE == "blacklist" and phone == TARGET_PHONE:
        is_authorized = False

    if not is_authorized:
        return make_yemot_response("id_list_message=t-אין לך הרשאה&goto_main=/")

    # פתיחת סשן (מצב) חדש לשיחה אם היא לא קיימת
    if call_id not in CALL_SESSIONS:
        CALL_SESSIONS[call_id] = {"step": "menu"}
        # מניעת דליפת זיכרון אם מצטברות יותר מדי שיחות
        if len(CALL_SESSIONS) > 100:
            CALL_SESSIONS.pop(next(iter(CALL_SESSIONS)))
            
    session = CALL_SESSIONS[call_id]
    step = session["step"]

    # פונקציה ששולפת תמיד את הקלט האחרון (מתמודדת עם הצטברות פרמטרים בימות)
    def get_last_param(param):
        vals = request.args.getlist(param)
        vals = [v for v in vals if v.strip()]
        return vals[-1] if vals else None

    res = ""

    # ניהול שלבי השיחה
    if step == "menu":
        selection = get_last_param("selection")
        if not selection:
            res = "read=t-לשירים חדשים הקש 1 לחיפוש קולי הקש 2=selection,1,1,1,7,st-javascript,y,no"
        elif selection == "1":
            session["query"] = "שירים חדשים 2024"
            res = process_search(session)
        elif selection == "2":
            session["step"] = "ask_query"
            res = "read=t-נא אמרו את שם השיר=query,1,1,1,7,st-voice,y,no"
        else:
            res = "read=t-לשירים חדשים הקש 1 לחיפוש קולי הקש 2=selection,1,1,1,7,st-javascript,y,no"

    elif step == "ask_query":
        query = get_last_param("query")
        if not query:
            res = "read=t-נא אמרו את שם השיר=query,1,1,1,7,st-voice,y,no"
        else:
            session["query"] = query
            res = process_search(session)

    elif step == "wait_choice":
        choice = get_last_param("choice")
        if not choice:
            res = generate_play_menu(session)
        elif choice == "1":
            res = process_play(session)
        else:
            # מקש אחר - עבור לתוצאה הבאה
            session["page"] += 1
            res = generate_play_menu(session)

    return make_yemot_response(res)


# --- פונקציות לוגיקה מאחורי הקלעים ---

def process_search(session):
    query = session.get("query", "")
    print("SEARCH:", query)
    
    info = get_cached_search(query)
    if not info:
        try:
            with yt_dlp.YoutubeDL(get_yt_options(True)) as ydl:
                info = ydl.extract_info(f"ytsearch10:{query}", download=False)
                set_cached_search(query, info)
        except Exception as e:
            print("SEARCH ERROR:", e)
            session["step"] = "menu"
            return "id_list_message=t-שגיאה בחיפוש&goto_main=/"

    entries = info.get("entries", [])
    valid_results = [e for e in entries if not is_filtered(e.get("title"))]

    if not valid_results:
        session["step"] = "menu"
        return "id_list_message=t-לא נמצאו תוצאות&goto_main=/"
    
    session["results"] = valid_results
    session["page"] = 0
    return generate_play_menu(session)


def generate_play_menu(session):
    results = session.get("results", [])
    page = session.get("page", 0)
    
    if page >= len(results):
        session["step"] = "menu"
        return "id_list_message=t-אין עוד תוצאות&goto_main=/"
    
    video = results[page]
    session["step"] = "wait_choice"
    return f"read=t-נמצא {video['title']}=choice,1,1,1,7,st-javascript,y,no"


def process_play(session):
    results = session.get("results", [])
    page = session.get("page", 0)
    
    if page >= len(results):
        return "id_list_message=t-שגיאה בניגון&goto_main=/"

    video = results[page]
    video_id = video["id"]

    try:
        with yt_dlp.YoutubeDL(get_yt_options(False)) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            session["step"] = "menu" # איפוס לאחר ניגון
            return f"play_url={info['url']}"
    except Exception as e:
        print("PLAY ERROR:", e)
        session["step"] = "menu"
        return "id_list_message=t-שגיאה בניגון&goto_main=/"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
