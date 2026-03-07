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
CALL_SESSIONS = {}

# --- בדיקת שרת ---
@app.route('/')
def home():
    return "SERVER_OK"

# --- הגדרות yt-dlp מעודכנות לעקיפת חסימות ---
def get_yt_options(is_search=True):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestaudio/best',
        # שימוש ב-User Agent של מכשיר אנדרואיד כדי להפחית חסימות
        'user_agent': 'Mozilla/5.0 (Android 14; Mobile; rv:128.0) Gecko/128.0 Firefox/128.0',
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extract_flat': is_search,
        'force_ipv4': True,
        'retries': 10,
        # שימוש בלקוח אינטרנט של אנדרואיד לעקיפת בוטים
        'extractor_args': {'youtube': {'player_client': ['android'], 'skip': ['dash', 'hls']}},
    }
    return opts

def is_filtered(text):
    if not text: return False
    return any(word.lower() in str(text).lower() for word in FORBIDDEN_WORDS)

def make_yemot_response(text):
    response = make_response(text + "\n")
    response.headers['Content-Type'] = "text/plain; charset=utf-8"
    return response

@app.route('/youtube', methods=['GET','POST'])
def main_logic():
    phone = request.args.get("ApiPhone", "").strip()
    call_id = request.args.get("ApiCallId", "")

    if request.args.get("hangup"):
        if call_id in CALL_SESSIONS: del CALL_SESSIONS[call_id]
        return make_response("")

    is_authorized = True
    if ACCESS_MODE == "whitelist" and phone != TARGET_PHONE:
        is_authorized = False
    
    if not is_authorized:
        return make_yemot_response("id_list_message=t-אין לך הרשאה&goto_main=/")

    if call_id not in CALL_SESSIONS:
        CALL_SESSIONS[call_id] = {"step": "menu", "page": 0}
            
    session = CALL_SESSIONS[call_id]
    
    def get_last_param(param):
        vals = request.args.getlist(param)
        return vals[-1] if vals else None

    # תפריט ראשי
    if session["step"] == "menu":
        selection = get_last_param("selection")
        if not selection:
            return make_yemot_response("read=t-לשירים חדשים הקש 1 לחיפוש קולי הקש 2=selection,1,1,1,7,st-javascript,y,no")
        
        if selection == "1":
            # חיפוש אוטומטי של שירים חדשים
            session["query"] = "שירים חדשים 2026"
            return process_search(session)
        elif selection == "2":
            session["step"] = "ask_query"
            # st-voice,y,no - הפקודה לזיהוי דיבור בימות המשיח
            return make_yemot_response("read=t-נא אמרו בקול רם את שם השיר=query,1,1,1,7,st-voice,y,no")

    # קבלת תוצאת חיפוש קולי
    elif session["step"] == "ask_query":
        query = get_last_param("query")
        if not query:
            return make_yemot_response("read=t-לא שמעתי, נא אמרו שוב את שם השיר=query,1,1,1,7,st-voice,y,no")
        session["query"] = query
        return process_search(session)

    # מעבר בין שירים (אם המשתמש ביקש שיר אחר)
    elif session["step"] == "wait_next":
        choice = get_last_param("choice")
        if choice == "2": # המשתמש רוצה שיר אחר
            session["page"] += 1
            return process_play(session)
        else:
            session["step"] = "menu"
            return make_yemot_response("goto_main=/")

    return make_yemot_response("goto_main=/")

def process_search(session):
    query = session.get("query", "")
    # שימוש ב-ytsearchdate כדי להביא את התוצאות הכי חדשות
    search_query = f"ytsearchdate10:{query}" 
    
    try:
        with yt_dlp.YoutubeDL(get_yt_options(True)) as ydl:
            info = ydl.extract_info(search_query, download=False)
            entries = info.get("entries", [])
            valid_results = [e for e in entries if not is_filtered(e.get("title"))]
            
            if not valid_results:
                return "id_list_message=t-לא נמצאו תוצאות&goto_main=/"
            
            session["results"] = valid_results
            session["page"] = 0
            # מעבר ישיר לניגון השיר הראשון
            return process_play(session)
            
    except Exception as e:
        print("SEARCH ERROR:", e)
        return "id_list_message=t-שגיאה בחיפוש&goto_main=/"

def process_play(session):
    results = session.get("results", [])
    page = session.get("page", 0)
    
    if page >= len(results):
        return "id_list_message=t-אין יותר שירים&goto_main=/"

    video = results[page]
    video_id = video["id"]

    try:
        with yt_dlp.YoutubeDL(get_yt_options(False)) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            url = info.get('url')
            title = info.get('title', 'שיר')
            
            # הודעה על השיר שמתנגן ואפשרות לעבור לשיר הבא בסיום/הקשה
            session["step"] = "wait_next"
            return f"id_list_message=t-מנגן כעת {title}&play_url={url}&read=t-לשיר הבא הקש 2=choice,1,1,1,7,st-javascript,y,no"
            
    except Exception as e:
        print("PLAY ERROR:", e)
        # אם שיר אחד חסום, מנסה אוטומטית את הבא בתור
        session["page"] += 1
        return process_play(session)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

