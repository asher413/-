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
RESULT_STORE = {}

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

def store_results(results):
    key = str(int(time.time()*1000))
    RESULT_STORE[key] = results
    if len(RESULT_STORE) > 50:
        RESULT_STORE.pop(next(iter(RESULT_STORE)))
    return key

def get_page(results, page, per_page=5):
    start = page * per_page
    end = start + per_page
    return results[start:end]

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

def build_target(base, params: dict):
    query = "&".join([f"{k}={quote(str(v))}" for k,v in params.items()])
    return f"{base}&{query}" if "?" in base else f"{base}?{query}"

@app.route('/youtube', methods=['GET','POST'])
def main_logic():

    phone = request.args.get("ApiPhone","").strip()
    step = request.args.get("step","menu")

    res = ""

    if request.args.get("hangup"):
        print("DEBUG: hangup")
        return make_response("")

    print(f"DEBUG phone={phone} step={step} args={request.args.to_dict()}")

    is_authorized = True
    if ACCESS_MODE == "whitelist" and phone != TARGET_PHONE:
        is_authorized = False
    elif ACCESS_MODE == "blacklist" and phone == TARGET_PHONE:
        is_authorized = False

    if not is_authorized:
        res = "id_list_message=t-אין לך הרשאה&goto_main=/"
        response = make_response(res + "\n")
        response.headers['Content-Type'] = "text/plain; charset=utf-8"
        return response

    if step == "menu":
        # אם יש כבר פרמטר selection זה אומר שהמשתמש הקיש תשובה
        if "selection" in request.args:
            # לוקחים את הערך האחרון למקרה שהצטברו פרמטרים
            selection = request.args.getlist("selection")[-1]
            if selection == "1":
                target = build_target("/youtube", {
                    "step": "search",
                    "query": "שירים חדשים 2024"
                })
                res = f"target={target}"

            elif selection == "2":
                # מעבירים לשלב נפרד כדי לשאול את השאלה באופן נקי
                res = "target=/youtube?step=ask_query"

            else:
                res = "goto_main=/"
        else:
            # תפריט ראשי
            res = "read=t-לשירים חדשים הקש 1 לחיפוש קולי הקש 2=selection,1,1,1,7,st-javascript,y,no"

    elif step == "ask_query":
        # אם יש query סימן שהוקלטה בקשה
        if "query" in request.args:
            query = request.args.getlist("query")[-1]
            target = build_target("/youtube", {
                "step": "search",
                "query": query
            })
            res = f"target={target}"
        else:
            res = "read=t-נא אמרו את שם השיר=query,1,1,1,7,st-voice,y,no"

    elif step == "search":
        query = request.args.get("query", "")
        print("SEARCH:", query)

        info = get_cached_search(query)

        if not info:
            try:
                with yt_dlp.YoutubeDL(get_yt_options(True)) as ydl:
                    info = ydl.extract_info(f"ytsearch10:{query}", download=False)
                    set_cached_search(query, info)
            except Exception as e:
                print("SEARCH ERROR:", e)
                return make_response("id_list_message=t-שגיאה בחיפוש&goto_main=/\n")

        entries = info.get("entries", [])
        valid_results = [e for e in entries if not is_filtered(e.get("title"))]

        if not valid_results:
            res = "id_list_message=t-לא נמצאו תוצאות&goto_main=/"
        else:
            store_key = store_results(valid_results)
            first_video = valid_results[0]
            
            # מעבירים לשלב נפרד לבחירה, כדי למנוע הצטברות פרמטרים על שלב החיפוש
            target = build_target("/youtube", {
                "step": "play_menu",
                "first_id": first_video["id"],
                "store": store_key,
                "page": 0
            })
            res = f"target={target}"

    elif step == "play_menu":
        store_key = request.args.get("store")
        page = int(request.args.get("page", 0))
        first_id = request.args.get("first_id")
        results = RESULT_STORE.get(store_key, [])

        if "choice" in request.args:
            choice = request.args.getlist("choice")[-1]
            if choice == "1":
                res = f"target=/youtube?step=get_link&vid={first_id}"
            else:
                page += 1
                page_results = get_page(results, page)

                if not page_results:
                    res = "id_list_message=t-אין עוד תוצאות&goto_main=/"
                else:
                    next_video = page_results[0]
                    target = build_target("/youtube", {
                        "step": "play_menu",
                        "first_id": next_video["id"],
                        "store": store_key,
                        "page": page
                    })
                    res = f"target={target}"
        else:
            page_results = get_page(results, page)
            if not page_results:
                res = "id_list_message=t-אין תוצאות&goto_main=/"
            else:
                video = page_results[0]
                res = f"read=t-נמצא {video['title']}=choice,1,1,1,7,st-javascript,y,no"

    elif step == "get_link":
        video_id = request.args.get("vid")
        try:
            with yt_dlp.YoutubeDL(get_yt_options(False)) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}",
                    download=False
                )
                res = f"play_url={info['url']}"

        except Exception as e:
            print("PLAY ERROR:", e)
            res = "id_list_message=t-שגיאה בניגון&goto_main=/"

    else:
        res = "goto_main=/"

    print("RESPONSE:", res)

    response = make_response(res + "\n")
    response.headers['Content-Type'] = "text/plain; charset=utf-8"
    return response


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
