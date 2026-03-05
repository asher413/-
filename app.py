from flask import Flask, request
import yt_dlp
import os

app = Flask(__name__)

# הגדרות מראש
ALLOWED_PHONE = "0534133753"  # המספר המורשה היחיד (או להפך לחסימה)
FORBIDDEN_WORDS = ["מילה1", "מילה2", "זמר_אסור"]

def get_youtube_results(query):
    ydl_opts = {'quiet': True, 'extract_flat': True, 'force_generic_ext': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # חיפוש של 20 תוצאות
        info = ydl.extract_info(f"ytsearch20:{query}", download=False)
        return info['entries']

@app.route('/youtube', methods=['GET', 'POST'])
def youtube_menu():
    phone = request.args.get("ApiPhone")
    
    # בדיקת הרשאה (חסימת מספר או אישור רק למספר ספציפי)
    if phone != ALLOWED_PHONE:
        return "id_list_message=t-אין לך הרשאה לשלוחה זו&goto_main=/"

    step = request.args.get("step", "main")
    
    # תפריט ראשי של יוטיוב
    if step == "main":
        return ("read=t-לשירים חדשים הקש 1 לחיפוש קולי הקש 2=selection,1,1,1,7,st-javascript,y,no"
                "&target=/youtube?step=handle_main")

    # טיפול בבחירה מהתפריט הראשי
    if step == "handle_main":
        selection = request.args.get("selection")
        if selection == "1":
            return f"target=/youtube?step=search&query=שירים חדשים"
        elif selection == "2":
            # הפעלה של זיהוי קולי בימות המשיח
            return "read=t-נא אמרו את שם השיר או הזמר=query,1,1,1,7,st-voice,y,no&target=/youtube?step=search"

    # ביצוע החיפוש
    if step == "search":
        query = request.args.get("query")
        results = get_youtube_results(query)
        
        # סינון תכנים
        filtered_results = []
        for res in results:
            title = res.get('title', '').lower()
            if not any(word in title for word in FORBIDDEN_WORDS):
                filtered_results.append(res)
        
        if not filtered_results:
            return "id_list_message=t-לא נמצאו תוצאות מתאימות&goto_main=/"

        # שמירת ה-ID של התוצאה הראשונה והשאר (בצורה פשוטה להדגמה)
        first_id = filtered_results[0]['id']
        first_title = filtered_results[0]['title']
        
        return (f"read=t-לתוצאה הראשונה {first_title} הקש 1 לשאר התוצאות הקש 2=results_choice,1,1,1,7,st-javascript,y,no"
                f"&first_id={first_id}&query={query}&target=/youtube?step=play_choice")

    # השמעת התוצאה
    if step == "play_choice":
        choice = request.args.get("results_choice")
        if choice == "1":
            video_id = request.args.get("first_id")
            # כאן המערכת צריכה להזרים את האודיו (דורש טיפול נוסף בהמרת לינק ל-MP3)
            return f"id_list_message=t-מפעיל את השיר&play_url=https://www.youtube.com/watch?v={video_id}"
        else:
            return "id_list_message=t-מעביר לרשימת התוצאות המלאה"

    return "goto_main=/"

if __name__ == '__main__':
    # Render מגדיר משתנה סביבה בשם PORT, אם הוא לא קיים נשתמש ב-5000 כברירת מחדל
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
