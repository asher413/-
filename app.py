# -*- coding: utf-8 -*-
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

# --- זיכרון זמני (Cache) למניעת חסימות ושיפור מהירות ---
SEARCH_CACHE = {}
CACHE_TIME = 300  # 5 דקות
RESULT_STORE = {}

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

# --- הגדרות yt-dlp נגד חסימות ---
def get_yt_options(is_search=True):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestaudio/best',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extract_flat': is_search,
        'force_ipv4': True,
        'retries': 5,
    }
    if os.path.exists('cookies.txt'):
        opts['cookiefile'] = 'cookies.txt'
    return opts

def is_filtered(text):
    if not text: return False
    return any(word.lower() in str(text).lower() for word in FORBIDDEN_WORDS)

def build_target(base, params: dict):
    query = "&".join([f"{k}={quote(str(v))}" for k,v in params.items()])
    return f"{base}&{query}" if "?" in base else f"{base}?{query}"

@app.route('/youtube', methods=['GET', 'POST'])
def main_logic():
    phone = request.args.get("ApiPhone", "").strip()
    step = request.args.get("step", "menu")
    selection = request.args.get("selection")
    res = ""

    # --- מעקף לשבירת לופים (אם המשתמש הקיש אך ה-step לא התעדכן) ---
    if selection and step == "menu":
        step = "handle_choice"

    # --- טיפול בניתוק שיחה ---
    if request.args.get("hangup") == "yes":
        return make_response("goto_main=/")
    
    # לוגים ל-Render
    print(f"DEBUG: Phone: {phone} | Step: {step} | Selection: {selection}")

    # --- 1. בדיקת הרשאה ---
    is_authorized = True
    if ACCESS_MODE == "whitelist" and phone != TARGET_PHONE:
        is_authorized = False
    elif ACCESS_MODE == "blacklist" and phone == TARGET_PHONE:
        is_authorized = False

    if not is_authorized:
        res = "id_list_message=t-אין לך הרשאה&goto_main=/"
        print("DEBUG: Status: Unauthorized")

    # --- 2. שלב התפריט הראשי ---
    elif step == "menu":
        res = "read=t-לשירים חדשים הקש 1. לחיפוש קולי הקש 2.=selection,1,1,1,7,st-javascript,y,no&target=/youtube?step=handle_choice"

    # --- 3. טיפול בבחירת המשתמש ---
    elif step == "handle_choice":
        if selection == "1":
            # העברה ישירה לחיפוש שירים חדשים
            target = build_target("/youtube", {"step": "search", "query": "שירים חדשים 2024"})
            res = f"target={target}"
        elif selection == "2":
            res = "read=t-נא אמרו את שם השיר או הזמר=query,1,1,1,7,st-voice,y,no&target=/youtube?step=search"
        else:
            res = "goto_main=/"

    # --- 4. ביצוע חיפוש ביוטיוב ---
    elif step == "search":
        query = request.args.get("query", "")
        print(f"DEBUG: Searching for: {query}")
        
        info = get_cached_search(query)
        if not info:
            try:
                with yt_dlp.YoutubeDL(get_yt_options(is_search=True)) as ydl:
                    info = ydl.extract_info(f"ytsearch20:{query}", download=False)
                    set_cached_search(query, info)
            except Exception as e:
                print(f"SEARCH ERROR: {e}")
                return make_response("id_list_message=t-שגיאה בחיפוש&goto_main=/")

        entries = info.get('entries', [])
        valid_results = [e for e in entries if not is_filtered(e.get('title'))]
        
        if not valid_results:
            res = "id_list_message=t-לא נמצאו תוצאות&goto_main=/"
        else:
            store_key = store_results(valid_results)
            page = 0
            page_results = get_page(valid_results, page)
            first_video = page_results[0]
            
            target = build_target("/youtube", {
                "step": "play_logic", 
                "first_id": first_video['id'], 
                "store": store_key, 
                "page": page
            })
            res = f"read=t-נמצא: {first_video['title']}. להשמעה הקש 1. לתוצאה הבאה הקש 2.=choice,1,1,1,7,st-javascript,y,no&target={target}"

    # --- 5. לוגיקת בחירת שיר מהתוצאות (דפדוף) ---
    elif step == "play_logic":
        choice = request.args.get("choice")
        store_key = request.args.get("store")
        page = int(request.args.get("page", 0))
        
        if choice == "1":
            video_id = request.args.get("first_id")
            res = f"target=/youtube?step=get_link&vid={video_id}"
        else:
            # מעבר לתוצאה הבאה
            page += 1
            results = RESULT_STORE.get(store_key, [])
            page_results = get_page(results, page)
            
            if not page_results:
                res = "id_list_message=t-אין עוד תוצאות&goto_main=/"
            else:
                next_video = page_results[0]
                target = build_target("/youtube", {
                    "step": "play_logic", 
                    "first_id": next_video['id'], 
                    "store": store_key, 
                    "page": page
                })
                res = f"read=t-נמצא: {next_video['title']}. להשמעה הקש 1. לתוצאה הבאה הקש 2.=choice,1,1,1,7,st-javascript,y,no&target={target}"

    # --- 6. הפקת לינק ישיר וניגון ---
    elif step == "get_link":
        video_id = request.args.get("vid")
        try:
            with yt_dlp.YoutubeDL(get_yt_options(is_search=False)) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                res = f"play_url={info['url']}"
        except Exception as e:
            print(f"PLAY ERROR: {e}")
            res = "id_list_message=t-שגיאה בניגון&goto_main=/"

    else:
        res = "goto_main=/"

    # החזרת תגובה נקייה לימות המשיח
    response = make_response(res)
    response.headers['Content-Type'] = 'text/plain; charset=utf-8'
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
