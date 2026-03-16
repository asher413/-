import os
import logging
from flask import Flask, request, make_response
import yt_dlp

# הגדרות לוגים
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
        'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}] if not is_search else []
    }

def make_yemot_response(text):
    """שליחת תשובה נקייה לימות המשיח"""
    res = make_response(text.strip() + "\n")
    res.headers['Content-Type'] = "text/plain; charset=utf-8"
    return res

@app.route('/youtube', methods=['GET', 'POST'])
def youtube_main():
    # שליפת נתונים - לוקחים תמיד את הערך האחרון ברשימה
    phone = request.args.getlist("ApiPhone")[-1] if request.args.getlist("ApiPhone") else ""
    call_id = request.args.getlist("ApiCallId")[-1] if request.args.getlist("ApiCallId") else "default"
    
    # בדיקת קלט - לוקחים את ה-v האחרון שנשלח
    v_list = request.args.getlist("v")
    user_input = v_list[-1].strip() if v_list else ""

    print(f"--- קריאה חדשה ---")
    print(f"CallID: {call_id} | Input: {user_input}")

    # הגנה בסיסית
    if phone != TARGET_PHONE and TARGET_PHONE != "":
        return make_yemot_response("id_list_message=t-אין הרשאה&goto_main=/")

    # ניהול ניתוק
    if request.args.get("hangup"):
        CALL_SESSIONS.pop(call_id, None)
        return make_response("")

    # יצירת סשן אם לא קיים
    if call_id not in CALL_SESSIONS:
        CALL_SESSIONS[call_id] = {"step": "menu", "page": 0, "results": []}
    
    session = CALL_SESSIONS[call_id]

    # --- לוגיקה ---

    # אם אנחנו בתפריט ואין קלט - נבקש קלט
    if session["step"] == "menu":
        if not user_input:
            print("Action: Sending Menu")
            return make_yemot_response("read=t-לשירים חדשים הקש 1. לחיפוש נא אמרו שם שיר=v,no,1,50,10,alpha")
        
        # אם יש קלט - עוברים לחיפוש
        session["query"] = "שירים חדשים 2026" if user_input == "1" else user_input
        session["step"] = "searching"
        print(f"Action: Searching for {session['query']}")
        return start_search(session)

    # אם אנחנו באמצע ניגון וממתינים לבחירה (שיר הבא/תפריט)
    elif session["step"] == "playing":
        print(f"Action: User chose {user_input} while playing")
        if user_input == "2":
            session["page"] += 1
            return play_video(session)
        elif user_input == "1":
            session.update({"step": "menu", "page": 0, "results": []})
            return make_yemot_response("read=t-נא אמרו שם שיר חדש=v,no,1,50,10,alpha")
        else:
            # אם המשתמש הקיש משהו אחר או שהזמן עבר, נשארים באותו מצב
            return play_video(session)

    return make_yemot_response("goto_main=/")

def start_search(session):
    query = session.get("query", "")
    try:
        with yt_dlp.YoutubeDL(get_yt_options(is_search=True)) as ydl:
            search_results = ydl.extract_info(f"ytsearch10:{query}", download=False).get("entries", [])
            session["results"] = [e for e in search_results if e]
            session["page"] = 0
            
            if not session["results"]:
                session["step"] = "menu"
                return make_yemot_response("id_list_message=t-לא נמצאו תוצאות&read=t-נסו חיפוש אחר=v,no,1,50,10,alpha")
            
            return play_video(session)
    except Exception as e:
        print(f"Search Error: {e}")
        return make_yemot_response("id_list_message=t-שגיאה בחיפוש&goto_main=/")

def play_video(session):
    idx = session["page"]
    results = session.get("results", [])

    if idx >= len(results):
        session["step"] = "menu"
        return make_yemot_response("id_list_message=t-סוף התוצאות&goto_main=/")

    video = results[idx]
    try:
        with yt_dlp.YoutubeDL(get_yt_options(is_search=False)) as ydl:
            info = ydl.extract_info(video['url'] if 'url' in video else f"https://www.youtube.com/watch?v={video['id']}", download=False)
            audio_url = info['url'].replace("&", "%26")
            title = info.get('title', 'שיר').replace(",", " ").replace("=", " ")
            
            session["step"] = "playing"
            print(f"Action: Playing {title}")
            
            # הפקודה המשולבת
            return make_yemot_response(
                f"id_list_message=t-מנגן {title[:40]}&"
                f"play_url={audio_url}&"
                f"read=t-לבא הקש 2 לתפריט 1=v,no,1,1,7,digits"
            )
    except Exception as e:
        print(f"Play Error: {e}")
        session["page"] += 1
        return play_video(session)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
