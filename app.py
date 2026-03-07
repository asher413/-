import os
import time
import threading
from flask import Flask, request, make_response
import yt_dlp
from urllib.parse import quote

app = Flask(__name__)

# ===============================
# הגדרות מערכת
# ===============================

ACCESS_MODE = "whitelist"
TARGET_PHONE = os.environ.get("TARGET_PHONE", "0534133753")

FORBIDDEN_WORDS = [
    "מילה_אסורה1",
    "תוכן_רע"
]

# ===============================
# CACHE
# ===============================

SEARCH_CACHE = {}
CACHE_TIME = 300

RESULT_STORE = {}
RESULT_TIMEOUT = 600

# ===============================
# בדיקת שרת ל Render
# ===============================

@app.route('/')
def home():
    return "SERVER_OK"

# ===============================
# ניקוי זיכרון
# ===============================

def cleanup_store():

    now = time.time()

    remove_keys = []

    for k,v in RESULT_STORE.items():

        if now - v["time"] > RESULT_TIMEOUT:
            remove_keys.append(k)

    for k in remove_keys:
        RESULT_STORE.pop(k,None)


# ניקוי כל כמה דקות
def cleanup_loop():

    while True:

        time.sleep(120)

        cleanup_store()


cleanup_thread = threading.Thread(target=cleanup_loop,daemon=True)
cleanup_thread.start()

# ===============================
# cache חיפוש
# ===============================

def get_cached_search(query):

    now = time.time()

    if query in SEARCH_CACHE:

        data, timestamp = SEARCH_CACHE[query]

        if now - timestamp < CACHE_TIME:

            return data

    return None


def set_cached_search(query,data):

    SEARCH_CACHE[query] = (data,time.time())


# ===============================
# שמירת תוצאות
# ===============================

def store_results(results):

    cleanup_store()

    key = str(int(time.time()*1000))

    RESULT_STORE[key] = {
        "results": results,
        "time": time.time()
    }

    if len(RESULT_STORE) > 100:
        RESULT_STORE.pop(next(iter(RESULT_STORE)))

    return key


def get_page(results,page,per_page=5):

    start = page * per_page
    end = start + per_page

    return results[start:end]


# ===============================
# yt-dlp options
# ===============================

def get_yt_options(is_search=True):

    opts = {

        'quiet': True,
        'no_warnings': True,

        'format': 'bestaudio/best',

        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',

        'nocheckcertificate': True,
        'geo_bypass': True,

        'extract_flat': is_search,

        'force_ipv4': True,

        'retries': 5,

        'socket_timeout': 20,

        'http_chunk_size': 10485760
    }

    if os.path.exists('cookies.txt'):
        opts['cookiefile'] = 'cookies.txt'

    return opts


# ===============================
# פילטר מילים
# ===============================

def is_filtered(text):

    if not text:
        return False

    text = str(text).lower()

    return any(word.lower() in text for word in FORBIDDEN_WORDS)


# ===============================
# בניית URL
# ===============================

def build_target(base,params:dict):

    query = "&".join(
        [f"{k}={quote(str(v))}" for k,v in params.items()]
    )

    if "?" in base:
        return f"{base}&{query}"

    return f"{base}?{query}"


# ===============================
# הלוגיקה הראשית
# ===============================

@app.route('/youtube',methods=['GET','POST'])
def main_logic():

    phone = request.args.get("ApiPhone","").strip()

    step = request.args.get("step","menu")

    selection = request.args.get("selection")

    res = ""

    # ===============================
    # טיפול בניתוק
    # ===============================

    if request.args.get("hangup"):

        print("DEBUG: hangup")

        return make_response("")

    # ===============================
    # מעקף לופ
    # ===============================

    if selection and step == "menu":
        step = "handle_choice"

    print(
        f"DEBUG phone={phone} "
        f"step={step} "
        f"selection={selection}"
    )

    # ===============================
    # בדיקת הרשאה
    # ===============================

    is_authorized = True

    if ACCESS_MODE == "whitelist" and phone != TARGET_PHONE:
        is_authorized = False

    if ACCESS_MODE == "blacklist" and phone == TARGET_PHONE:
        is_authorized = False

    if not is_authorized:

        res = "id_list_message=t-אין לך הרשאה&goto_main=/"

    # ===============================
    # תפריט
    # ===============================

    elif step == "menu":

        res = (
            "read=t-לשירים חדשים הקש 1. לחיפוש קולי הקש 2."
            "=selection,1,1,1,7,st-javascript,y,no"
            "&target=/youtube?step=handle_choice"
        )

    # ===============================
    # בחירה
    # ===============================

    elif step == "handle_choice":

        if selection == "1":

            target = build_target(
                "/youtube",
                {
                    "step":"search",
                    "query":"שירים חדשים 2024"
                }
            )

            res = f"target={target}"

        elif selection == "2":

            res = (
                "read=t-נא אמרו את שם השיר או הזמר"
                "=query,1,1,1,7,st-voice,y,no"
                "&target=/youtube?step=search"
            )

        else:

            res = "goto_main=/"

    # ===============================
    # חיפוש
    # ===============================

    elif step == "search":

        query = request.args.get("query","")

        print("SEARCH:",query)

        info = get_cached_search(query)

        if not info:

            try:

                with yt_dlp.YoutubeDL(
                    get_yt_options(True)
                ) as ydl:

                    info = ydl.extract_info(
                        f"ytsearch10:{query}",
                        download=False
                    )

                    set_cached_search(query,info)

            except Exception as e:

                print("SEARCH ERROR:",e)

                return make_response(
                    "id_list_message=t-שגיאה בחיפוש&goto_main=/"
                )

        entries = info.get("entries",[])

        valid_results = [
            e for e in entries
            if not is_filtered(e.get("title"))
        ]

        if not valid_results:

            res = "id_list_message=t-לא נמצאו תוצאות&goto_main=/"

        else:

            store_key = store_results(valid_results)

            page = 0

            page_results = get_page(valid_results,page)

            if not page_results:

                res = "id_list_message=t-אין תוצאות&goto_main=/"

            else:

                first_video = page_results[0]

                target = build_target(
                    "/youtube",
                    {
                        "step":"play_logic",
                        "first_id":first_video["id"],
                        "store":store_key,
                        "page":page
                    }
                )

                res = (
                    f"read=t-נמצא {first_video['title']}."
                    " להשמעה הקש 1."
                    " לתוצאה הבאה הקש 2."
                    "=choice,1,1,1,7,st-javascript,y,no"
                    f"&target={target}"
                )

    # ===============================
    # דפדוף
    # ===============================

    elif step == "play_logic":

        choice = request.args.get("choice")

        store_key = request.args.get("store")

        page = int(request.args.get("page",0))

        results_data = RESULT_STORE.get(store_key)

        if not results_data:

            return make_response(
                "id_list_message=t-החיפוש פג תוקף&goto_main=/"
            )

        results = results_data["results"]

        if choice == "1":

            video_id = request.args.get("first_id")

            res = f"target=/youtube?step=get_link&vid={video_id}"

        else:

            page += 1

            page_results = get_page(results,page)

            if not page_results:

                res = "id_list_message=t-אין עוד תוצאות&goto_main=/"

            else:

                next_video = page_results[0]

                target = build_target(
                    "/youtube",
                    {
                        "step":"play_logic",
                        "first_id":next_video["id"],
                        "store":store_key,
                        "page":page
                    }
                )

                res = (
                    f"read=t-נמצא {next_video['title']}."
                    " להשמעה הקש 1."
                    " הבא הקש 2."
                    "=choice,1,1,1,7,st-javascript,y,no"
                    f"&target={target}"
                )

    # ===============================
    # ניגון
    # ===============================

    elif step == "get_link":

        video_id = request.args.get("vid")

        try:

            with yt_dlp.YoutubeDL(
                get_yt_options(False)
            ) as ydl:

                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}",
                    download=False
                )

                res = f"play_url={info['url']}"

        except Exception as e:

            print("PLAY ERROR:",e)

            res = (
                "id_list_message=t-שגיאה בניגון"
                "&goto_main=/"
            )

    else:

        res = "goto_main=/"

    response = make_response(res)

    response.headers['Content-Type'] = "text/plain; charset=utf-8"

    return response


# ===============================
# הרצת השרת
# ===============================

if __name__ == "__main__":

    port = int(os.environ.get("PORT",10000))

    print("SERVER STARTING ON PORT",port)

    app.run(
        host="0.0.0.0",
        port=port,
        threaded=True
    )
