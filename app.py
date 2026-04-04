# Full Flask IVR system using Invidious (no yt-dlp, no blocks, fast) - Code by LEMON SHLIF
import os
import time
import logging
import requests
from flask import Flask, request, make_response

# --- לוגים ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- בדיקות ---
@app.route("/")
def home_page():
    return "OK"

@app.route("/health")
def health_check():
    return "SERVER_OK"

# --- הגדרות ---
TARGET_PHONE = "0534133753"
FORBIDDEN_WORDS = ["מילה_אסורה1", "תוכן_רע"]
CALL_SESSIONS = {}
SEARCH_CACHE = {}
CACHE_TIME = 300

# 🔥 שרת Invidious (אפשר להחליף אם נופל)
INVIDIOUS_SERVERS = [
    "https://vid.puffyan.us/api/v1",
    "https://inv.nadeko.net/api/v1",
    "https://invidious.slipfox.xyz/api/v1",
    "https://inv.tux.pizza/api/v1"
]

CURRENT_INVIDIOUS = 0

AUDIO_CACHE = {}

def is_filtered(text):
    if not text:
        return False
    return any(word in text for word in FORBIDDEN_WORDS)

def make_yemot_response(text):
    logger.info(f"RESPONSE: {text}")
    response = make_response(text + "\n")
    response.headers['Content-Type'] = "text/plain; charset=utf-8"
    return response

# --- API ---
@app.route('/youtube', methods=['GET', 'POST'])
def youtube_api():
    phone = request.args.get("ApiPhone", "").strip()
    call_id = request.args.get("ApiCallId", "")
    selection = request.args.get("selection")
    query = request.args.get("query")
    choice = request.args.get("choice")

    logger.info(f"DEBUG phone={phone} | step={CALL_SESSIONS.get(call_id, {}).get('step')}")

    if phone != TARGET_PHONE:
        return make_yemot_response("id_list_message=t-אין הרשאה&goto_main=/")

    if request.args.get("hangup"):
        CALL_SESSIONS.pop(call_id, None)
        return make_yemot_response("goto_main=/")

    if call_id not in CALL_SESSIONS:
        CALL_SESSIONS[call_id] = {"step": "menu", "page": 0, "results": []}

    session = CALL_SESSIONS[call_id]

    # לא לאפס באמצע ניגון
    if not selection and not query and not choice:
        if session.get("step") != "waiting_next":
            session["step"] = "menu"
            return make_yemot_response(
                "read=t-לשירים חדשים הקש 1 לחיפוש קולי הקש 2=selection,1,1,1,7,st-digits,y,no"
            )

    if selection == "1" and session["step"] == "menu":
        session["query"] = "שירים חדשים"
        session["step"] = "searching"
        return start_search(session)

    if selection == "2" and session["step"] == "menu":
        session["step"] = "ask_query"
        return make_yemot_response("read=t-נא אמרו את שם השיר=query,1,1,1,7,st-voice,y,no")

    if query and session["step"] == "ask_query":
        session["query"] = query
        session["step"] = "searching"
        return start_search(session)

    if choice == "2":
        session["page"] += 1
        return play_current_video(session)

    if choice == "1":
        session["step"] = "menu"
        return make_yemot_response("goto_main=/")

    return make_yemot_response("goto_main=/")

# --- חיפוש דרך Invidious ---
def start_search(session):
    query = session.get("query", "שירים")

    now = time.time()
    if query in SEARCH_CACHE:
        data, timestamp = SEARCH_CACHE[query]
        if now - timestamp < CACHE_TIME:
            session["results"] = data
            session["page"] = 0
            return play_current_video(session)

    try:
        url = f"{INVIDIOUS_API}/search"
        params = {
            "q": query,
            "type": "video",
            "sort_by": "upload_date"
        }

        res = requests.get(url, params=params, timeout=5)
        data = res.json()

        results = []
        for v in data:
            if not is_filtered(v.get("title")):
                results.append({
                    "id": v.get("videoId"),
                    "title": v.get("title")
                })

        if not results:
            return make_yemot_response("id_list_message=t-לא נמצאו תוצאות&goto_main=/")

        session["results"] = results
        session["page"] = 0

        SEARCH_CACHE[query] = (results, now)

        return play_current_video(session)

    except Exception as e:
        logger.error(f"SEARCH ERROR: {e}")
        return make_yemot_response("id_list_message=t-שגיאה בחיפוש&goto_main=/")

# --- שליפת סטרים ---
def get_audio_url(video_id):
    try:
        url = f"{INVIDIOUS_API}/videos/{video_id}"
        res = requests.get(url, timeout=5)
        data = res.json()

        formats = data.get("adaptiveFormats", [])

        for f in formats:
            if f.get("type", "").startswith("audio"):
                return f.get("url")

    except Exception as e:
        logger.error(f"AUDIO ERROR: {e}")

    return None

# --- ניגון ---
def play_current_video(session):
    results = session.get("results", [])
    page = session.get("page", 0)

    attempts = 0
    while page < len(results) and attempts < 5:
        video = results[page]
        video_id = video["id"]
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

        page += 1
        attempts += 1

    session["step"] = "menu"
    return make_yemot_response("id_list_message=t-לא ניתן לנגן כרגע&goto_main=/")

# --- הרצה ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
