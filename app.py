# Full improved Flask YouTube IVR system with fixes for session reset, yt-dlp 429, and date-based search - Code by LEMON SHLIF
import os
import time
import logging
from flask import Flask, request, make_response
import yt_dlp

# --- לוגים ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- בדיקות בריאות ---
@app.route("/")
def home_page():
    return "OK"

@app.route("/health")
def health_check():
    return "SERVER_OK"

# --- הגדרות כלליות ---
ACCESS_MODE = "whitelist"
TARGET_PHONE = "0534133753"
FORBIDDEN_WORDS = ["מילה_אסורה1", "תוכן_רע"]
SEARCH_CACHE = {}
CACHE_TIME = 300
CALL_SESSIONS = {}
MAX_RETRIES = 3

# --- yt-dlp options (משופר נגד חסימות 429) ---
def get_yt_options(is_search=True):
    return {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestaudio/best',
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extract_flat': is_search,
        'force_ipv4': True,
        'retries': 3,
        'noplaylist': True,
        'sleep_interval_requests': 1,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        },
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
            }
        }
    }

def is_filtered(text):
    if not text:
        return False
    return any(word in text for word in FORBIDDEN_WORDS)

def make_yemot_response(text):
    logger.info(f"RESPONSE: {text}")
    response = make_response(text + "\n")
    response.headers['Content-Type'] = "text/plain; charset=utf-8"
    return response

# --- API מרכזי ---
@app.route('/youtube', methods=['GET', 'POST'])
@app.route('/ivr', methods=['GET', 'POST'])
def youtube_api():
    phone = request.args.get("ApiPhone", "").strip()
    call_id = request.args.get("ApiCallId", "")
    selection = request.args.get("selection")
    query = request.args.get("query")
    choice = request.args.get("choice")

    logger.info(f"DEBUG phone={phone} | step={CALL_SESSIONS.get(call_id, {}).get('step')}")

    # הרשאה
    if phone != TARGET_PHONE:
        return make_yemot_response("id_list_message=t-אין לך הרשאה&goto_main=/")

    # ניתוק
    if request.args.get("hangup"):
        CALL_SESSIONS.pop(call_id, None)
        return make_yemot_response("goto_main=/")

    # יצירת סשן
    if call_id not in CALL_SESSIONS:
        CALL_SESSIONS[call_id] = {"step": "menu", "page": 0, "results": []}

    session = CALL_SESSIONS[call_id]

    # 🔥 תיקון: לא לאפס בזמן ניגון
    if not selection and not query and not choice:
        if session.get("step") != "waiting_next":
            session["step"] = "menu"
            return make_yemot_response(
                "read=t-לשירים חדשים הקש 1 לחיפוש קולי הקש 2=selection,1,1,1,7,st-digits,y,no"
            )

    # תפריט
    if selection == "1" and session["step"] == "menu":
        session["query"] = "שירים חדשים"
        session["step"] = "searching"
        return start_search(session)

    if selection == "2" and session["step"] == "menu":
        session["step"] = "ask_query"
        return make_yemot_response("read=t-נא אמרו את שם השיר=query,1,1,1,7,st-voice,y,no")

    # חיפוש קולי
    if query and session["step"] == "ask_query":
        session["query"] = query
        session["step"] = "searching"
        return start_search(session)

    # מעבר שירים
    if choice == "2":
        session["page"] += 1
        return play_current_video(session)

    if choice == "1":
        session["step"] = "menu"
        return make_yemot_response("goto_main=/")

    return make_yemot_response("goto_main=/")

# --- חיפוש עם CACHE + retry ---
# חיפוש + מיון לפי תאריך (חדש קודם) בלי ytsearchdate - Code by LEMON SHLIF
def start_search(session):
    query = session.get("query", "שירים")

    now = time.time()
    if query in SEARCH_CACHE:
        data, timestamp = SEARCH_CACHE[query]
        if now - timestamp < CACHE_TIME:
            session["results"] = data
            session["page"] = 0
            return play_current_video(session)

    search_string = f"ytsearch10:{query}"

    for attempt in range(MAX_RETRIES):
        try:
            with yt_dlp.YoutubeDL(get_yt_options(True)) as ydl:
                info = ydl.extract_info(search_string, download=False)

            entries = info.get("entries", [])

            # 🔥 סינון
            results = [e for e in entries if not is_filtered(e.get("title"))]

            # 🔥 מיון לפי תאריך (חדש קודם)
            results.sort(
                key=lambda x: x.get("upload_date") or "0",
                reverse=True
            )

            if not results:
                return make_yemot_response("id_list_message=t-לא נמצאו תוצאות&goto_main=/")

            session["results"] = results
            session["page"] = 0

            SEARCH_CACHE[query] = (results, now)

            return play_current_video(session)

        except Exception as e:
            logger.error(f"SEARCH ERROR attempt {attempt}: {e}")
            time.sleep(2)

    return make_yemot_response("id_list_message=t-שגיאה בחיפוש&goto_main=/")

# --- שליפת אודיו ישיר (בלי סטרימינג) ---
# שליפת אודיו עם timeout והגנה מקריסה - Code by LEMON SHLIF
def get_audio_url(video_id):
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"

        ydl_opts = get_yt_options(False)
        ydl_opts.update({
            'socket_timeout': 5,
        })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            for f in info.get("formats", []):
                if f.get("acodec") != "none":
                    return f.get("url")

    except Exception as e:
        logger.error(f"AUDIO ERROR: {e}")

    return None

# --- ניגון ---
# ניגון בלי קריסה + דילוג בטוח על שירים חסומים - Code by LEMON SHLIF
def play_current_video(session):
    results = session.get("results", [])
    page = session.get("page", 0)

    max_attempts = 5
    attempts = 0

    while page < len(results) and attempts < max_attempts:
        video = results[page]
        video_id = video['id']
        title = video.get("title", "שיר")

        audio_url = get_audio_url(video_id)

        if audio_url:
            session["page"] = page
            session["step"] = "waiting_next"

            return make_yemot_response(
                f"id_list_message=t-מנגן כעת {title}&"
                f"play_url={audio_url}&"
                f"read=t-לשיר הבא הקש 2 לתפריט הקש 1=choice,1,1,1,7,st-javascript,y,no"
            )

        # אם נחסם → דלג
        page += 1
        attempts += 1

    # אם לא נמצא כלום
    session["step"] = "menu"
    return make_yemot_response("id_list_message=t-לא ניתן לנגן כרגע נסה שוב&goto_main=/")

# --- הרצה ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
