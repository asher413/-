import os
import logging
from flask import Flask, request, make_response
import yt_dlp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TARGET_PHONE = "0534133753"
FORBIDDEN_WORDS = ["מילה_אסורה1", "תוכן_פוגעני"]

CALL_SESSIONS = {}

def is_filtered(text):
    if not text:
        return False
    text = str(text).lower()
    return any(word.lower() in text for word in FORBIDDEN_WORDS)

def make_yemot_response(text):
    logger.info(f"Sending: {text}")
    resp = make_response(text + "\n")
    resp.headers['Content-Type'] = "text/plain; charset=utf-8"
    return resp

def get_input(param):
    vals = request.args.getlist(param)
    return vals[-1] if vals else None

def get_yt_options(is_search=True):
    return {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestaudio/best',
        'user_agent': 'Mozilla/5.0 (Android 14; Mobile; rv:128.0) Gecko/128.0 Firefox/128.0',
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extract_flat': is_search,
        'force_ipv4': True,
        'retries': 10,
        'extractor_args': {'youtube': {'player_client': ['android'], 'skip': ['dash', 'hls']}},
    }

@app.route('/')
def home():
    return "SERVER_OK"

@app.route('/youtube', methods=['GET', 'POST'])
def youtube():
    phone = request.args.get("ApiPhone", "").strip()
    call_id = request.args.get("ApiCallId", "")

    if phone != TARGET_PHONE:
        return make_yemot_response("id_list_message=t-אין הרשאה&goto_main=/")

    if request.args.get("hangup"):
        CALL_SESSIONS.pop(call_id, None)
        return make_response("")

    if call_id not in CALL_SESSIONS:
        CALL_SESSIONS[call_id] = {"step": "menu", "page": 0, "results": []}

    session = CALL_SESSIONS[call_id]

    # כאן ממשיך הלוגיקה של התפריטים...
    # (הוסף את שאר הקוד המתוקן של התפריטים, החיפוש והניגון)

    # לדוגמה זמני – תפריט ראשוני
    if session["step"] == "menu":
        selection = get_input("selection")
        if not selection:
            return make_yemot_response(
                "read=t-לשירים חדשים הקש 1, לחיפוש קולי אמרו את השם לאחר הצליל="
                "selection,1,1,1,7,st-voice,y,no"
            )
        # המשך משם...

    return make_yemot_response("id_list_message=t-שגיאה כללית&goto_main=/")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
