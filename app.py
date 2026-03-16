import os
import logging
from flask import Flask, request, make_response
import yt_dlp

# הגדרת לוגים בסיסית
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- הגדרות ---
TARGET_PHONE = "0534133753"
CALL_SESSIONS = {}

@app.route('/')
def health_check():
    return "OK", 200

def get_yt_options(is_search=True):
    return {
        'quiet': True,
        'format': 'bestaudio/best',
        'extract_flat': is_search,
        'force_ipv4': True,
        'nocheckcertificate': True,
    }

def make_yemot_response(text):
    """שולח תגובה נקייה ומדפיס אותה ללוג כדי שנוכל לדבג"""
    response_text = text.strip()
    print(f"DEBUG RESPONSE: {response_text}") # זה יופיע ב-Logs ב-Render
    res = make_response(response_text + "\n")
    res.headers['Content-Type'] = "text/plain; charset=utf-8"
    return res

@app.route('/youtube', methods=['GET', 'POST'])
def youtube_main():
    phone = request.args.get("ApiPhone", "").strip()
    call_id = request.args.get("ApiCallId", "")
    
    # סינון מספר טלפון
    if phone != TARGET_PHONE:
        return make_yemot_response("id_list_message=t-אין הרשאה&goto_main=/")

    # ניקוי סשן בניתוק
    if request.args.get("hangup"):
        CALL_SESSIONS.pop(call_id, None)
        return make_response("")

    if call_id not in CALL_SESSIONS:
        CALL_SESSIONS[call_id] = {"step": "menu", "page": 0}
    
    session = CALL_SESSIONS[call_id]
    user_input = request.args.get("v", "").strip()

    # --- שלב 1: תפריט ראשי ---
    if session["step"] == "menu":
        if not user_input:
            # שימוש ב-alpha כדי לקבל גם דיבור וגם הקשות
            return make_yemot_response("read=t-לשירים חדשים הקש 1. לחיפוש נא אמרו שם שיר=v,no,1,50,10,alpha")

        session["query"] = "שירים חדשים 2026" if user_input == "1" else user_input
        return start_search(session)

    # --- שלב 2: שליטה בזמן ניגון ---
    elif session["step"] == "playing":
        if user_input == "2": # שיר הבא
            session["page"] += 1
            return play_video(session)
        elif user_input == "1": # חזרה לתפריט
            session.update({"step": "menu", "page": 0})
            return make_yemot_response("read=t-נא אמרו שם שיר חדש לחיפוש=v,no,1,50,10,alpha")

    return make_yemot_response("goto_main=/")

def start_search(session):
    query = session.get("query", "")
    try:
        with yt_dlp.YoutubeDL(get_yt_options(is_search=True)) as ydl:
            search_results = ydl.extract_info(f"ytsearch10:{query}", download=False).get("entries", [])
            session["results"] = [e for e in search_results if e]
            session["page"] = 0
            
            if not session["results"]:
                return make_yemot_response("id_list_message=t-לא נמצאו תוצאות&goto_main=/")
            
            return play_video(session)
    except Exception as e:
        print(f"ERROR Search: {e}")
        return make_yemot_response("id_list_message=t-שגיאה בחיפוש&goto_main=/")

def play_video(session):
    idx = session["page"]
    results = session.get("results", [])

    if idx >= len(results):
        return make_yemot_response("id_list_message=t-סוף התוצאות&goto_main=/")

    video = results[idx]
    try:
        with yt_dlp.YoutubeDL(get_yt_options(is_search=False)) as ydl:
            info = ydl.extract_info(video['url'], download=False)
            audio_url = info['url'].replace("&", "%26")
            title = info.get('title', 'שיר').replace(",", " ").replace("=", " ")
            
            session["step"] = "playing"
            
            # בניית הפקודה בצורה הכי פשוטה שיש
            return make_yemot_response(
                f"id_list_message=t-מנגן {title[:50]}&"
                f"play_url={audio_url}&"
                f"read=t-לשיר הבא הקש 2 לתפריט 1=v,no,1,1,7,digits"
            )
    except Exception as e:
        print(f"ERROR Play: {e}")
        session["page"] += 1
        return play_video(session)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
