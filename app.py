import os
import time
import logging
from flask import Flask, request, make_response
import yt_dlp
from urllib.parse import quote
import requests

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

# --- yt-dlp options ---
def get_yt_options(is_search=True):
    return {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extract_flat': is_search,
        'force_ipv4': True,
        'retries': 5,
        'noplaylist': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
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

    logger.info(f"DEBUG phone={phone}")

    # הרשאה
    if phone != TARGET_PHONE:
        return make_yemot_response("id_list_message=t-אין לך הרשאה&goto_main=/")

    # ניתוק
    if request.args.get("hangup"):
        CALL_SESSIONS.pop(call_id, None)
        return make_yemot_response("goto_main=/")

    # יצירת סשן
    if call_id not in CALL_SESSIONS:
        CALL_SESSIONS[call_id] = {
            "step": "menu",
            "page": 0,
            "results": []
        }

    session = CALL_SESSIONS[call_id]

    def get_input(name):
        vals = request.args.getlist(name)
        return vals[-1] if vals else None

    # --- תפריט ---
    if session["step"] == "menu":
        selection = get_input("selection")

        if not selection:
            return make_yemot_response(
                "read=t-לשירים חדשים הקש 1 לחיפוש קולי הקש 2=selection,1,1,1,7,st-digits,y,no"
            )

        if selection == "1":
            session["query"] = "שירים חדשים 2026"
            return start_search(session)

        elif selection == "2":
            session["step"] = "ask_query"
            return make_yemot_response(
                "read=t-נא אמרו את שם השיר=query,1,1,1,7,st-voice,y,no"
            )

    elif session["step"] == "ask_query":
        query = get_input("query")

        if not query:
            return make_yemot_response(
                "read=t-לא שמעתי, נא אמרו שוב=query,1,1,1,7,st-voice,y,no"
            )

        session["query"] = query
        return start_search(session)

    elif session["step"] == "waiting_next":
        choice = get_input("choice")

        if choice == "2":
            session["page"] += 1
            return play_current_video(session)

        elif choice == "1":
            session["step"] = "menu"
            return make_yemot_response("goto_main=/")

        else:
            return play_current_video(session)

    return make_yemot_response("goto_main=/")

# --- חיפוש ---
def start_search(session):
    query = session.get("query", "שירים")
    search_string = f"ytsearch10:{query}"

    try:
        with yt_dlp.YoutubeDL(get_yt_options(True)) as ydl:
            info = ydl.extract_info(search_string, download=False)

        entries = info.get("entries", [])
        results = [e for e in entries if not is_filtered(e.get("title"))]

        if not results:
            return make_yemot_response("id_list_message=t-לא נמצאו תוצאות&goto_main=/")

        session["results"] = results
        session["page"] = 0

        return play_current_video(session)

    except Exception as e:
        logger.error(f"SEARCH ERROR: {e}")
        return make_yemot_response("id_list_message=t-שגיאה בחיפוש&goto_main=/")

# --- ניגון ---
def play_current_video(session, retries=0):
    results = session.get("results", [])
    page = session.get("page", 0)

    if page >= len(results):
        session["step"] = "menu"
        return make_yemot_response("id_list_message=t-אין עוד תוצאות&goto_main=/")

    video = results[page]
    video_id = video['id']
    title = video.get("title", "שיר")

    try:
        servers = [
            "https://invidious.fdn.fr",
            "https://inv.nadeko.net",
            "https://invidious.privacydev.net"
        ]

        audio_url = None

        for server in servers:
            try:
                api_url = f"{server}/api/v1/videos/{video_id}"
                r = requests.get(api_url, timeout=5)

                if r.status_code != 200:
                    continue

                data = r.json()

                for f in data.get("adaptiveFormats", []):
                    if "audio" in f.get("type", ""):
                        audio_url = f.get("url")
                        break

                if audio_url:
                    break

            except Exception as e:
                logger.error(f"SERVER FAILED {server}: {e}")
                continue

        if not audio_url:
            raise Exception("ALL SERVERS FAILED")

        session["step"] = "waiting_next"

        return make_yemot_response(
            f"id_list_message=t-מנגן כעת {title}&"
            f"play_url={audio_url}&"
            f"read=t-לשיר הבא הקש 2 לתפריט הקש 1=choice,1,1,1,7,st-javascript,y,no"
        )

    except Exception as e:
        logger.error(f"PLAY ERROR: {e}")
        if retries >= MAX_RETRIES:
            session["step"] = "menu"
            return make_yemot_response("id_list_message=t-אין אפשרות לנגן את השיר&goto_main=/")
        session["page"] += 1
        return play_current_video(session, retries=retries+1)

# --- הרצה ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
