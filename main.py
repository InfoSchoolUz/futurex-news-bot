import feedparser
import google.generativeai as genai
import requests
import json
import os
import hashlib
import time
from datetime import datetime
from difflib import SequenceMatcher

# ============================================================
# TIZIM SOZLAMALARI
# ============================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "@futurex_1984")

# ============================================================
# ISHONCHLI XALQARO MANBALAR (INGLIZ VA RUS TILLARIDA)
# ============================================================
RSS_SOURCES = [
    # 1. Komponentlar, platalar va mikrosxemalar (Mikro-daraja)
    {"name": "Arduino Robotics",         "url": "https://blog.arduino.cc/category/robotics/feed/"},
    {"name": "Raspberry Pi Foundation",  "url": "https://www.raspberrypi.org/feed/"},
    
    # 2. Gumanoid robotlar va Jismoniy AI (Neo, Atlas, Optimus)
    {"name": "1X Technologies (NEO)",   "url": "https://www.1x.tech/blog/rss.xml"},
    {"name": "Boston Dynamics",          "url": "https://bostondynamics.com/feed/"},
    {"name": "Agility Robotics (Digit)", "url": "https://www.agilityrobotics.com/news/rss.xml"},
    
    # 3. Sanoat avtomatizatsiyasi va Laboratoriyalar
    {"name": "MIT Robotics Lab",         "url": "https://biomimeticrobotics.mit.edu/feed"},
    {"name": "IEEE Spectrum Robotics",   "url": "https://spectrum.ieee.org/feeds/robotics.xml"},
    {"name": "Habr Robotics (Ruscha)",   "url": "https://habr.com/ru/rss/hub/robot/all/?fl=ru"},
    
    # 4. Kosmik AI va Avtonom Tizimlar (Makro-daraja)
    {"name": "NASA News Releases",       "url": "https://www.nasa.gov/news-release/feed/"},
    {"name": "ESA Space Science",        "url": "https://www.esa.int/rssfeed/Our_Activities/Space_Science"}
]

SENT_NEWS_FILE = "sent_news.json"
SIMILARITY_THRESHOLD = 0.55 

# ============================================================
# KESH TIZIMI (JSON)
# ============================================================
def load_sent_news():
    if os.path.exists(SENT_NEWS_FILE):
        with open(SENT_NEWS_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                return data if isinstance(data, list) else []
            except Exception:
                return []
    return []

def save_sent_news(sent_list):
    unique_list = list(set(sent_list))
    with open(SENT_NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(unique_list[-500:], f, ensure_ascii=False, indent=2)

def get_news_hash(title):
    return hashlib.md5(title.lower().strip().encode('utf-8')).hexdigest()

def is_similar(title1, title2):
    return SequenceMatcher(None, title1.lower(), title2.lower()).ratio() > SIMILARITY_THRESHOLD

# ============================================================
# SKANER ENGINE
# ============================================================
def fetch_all_news():
    all_news = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    for source in RSS_SOURCES:
        try:
            response = requests.get(source["url"], headers=headers, timeout=15)
            if response.status_code == 200:
                feed = feedparser.parse(response.content)
                count = 0
                for entry in feed.entries[:12]:
                    title = entry.get("title", "").strip()
                    link = entry.get("link", "").strip()
                    summary = entry.get("summary", entry.get("description", "")).strip()
                    if title and link:
                        all_news.append({
                            "title": title,
                            "link": link,
                            "summary": summary[:700] if summary else "",
                            "source": source["name"],
                            "hash": get_news_hash(title)
                        })
                        count += 1
                print(f"✅ {source['name']}: {count} ta ma'lumot yuklandi.")
            else:
                print(f"⚠️ {source['name']} (Status kod: {response.status_code})")
        except Exception as e:
            print(f"❌ {source['name']} ulanishda xatolik: {e}")
    return all_news

def group_similar_news(news_list):
    groups = []
    used = set()
    for i, news in enumerate(news_list):
        if i in used:
            continue
        group = [news]
        used.add(i)
        for j, other in enumerate(news_list):
            if j in used:
                continue
            if is_similar(news["title"], other["title"]):
                group.append(other)
                used.add(j)
        groups.append(group)
    return groups

# ============================================================
# GEMINI AI - SOF O'ZBEK TILIDAGI TAHLIL (BO'RTTIRISHLARSIZ)
# ============================================================
def generate_summary_with_gemini(news_group):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.0-flash")

    titles = [n["title"] for n in news_group]
    summaries = [n["summary"] for n in news_group if n["summary"]]
    sources = list(set([n["source"] for n in news_group]))

    prompt = f"""You are an expert, realistic, and highly accurate technical analysis system for the 'FutureX' channel.
Your task is to analyze the following news articles (which may be in English or Russian) and determine if they are strictly related to:
1. Microelectronics/components for hardware (Arduino, Raspberry Pi, chips, sensory systems).
2. Advanced robotics, embodiments, cybernetics, and humanoids (NEO, Atlas, Digit, industry automation).
3. Space technology integrated with Artificial Intelligence, autonomous space probes, rovers, orbital AI data crunching.

Input Materials:
Titles:
{chr(10).join(f'- {t}' for t in titles)}

Summaries:
{chr(10).join(f'- {s}' for s in summaries[:3])}

STRICT INSTRUCTIONS:
1. Filter out general software, politics, regular consumer gadgets (like smartphones or laptops), or standard economy news. If it doesn't fit the themes above, reply with exactly one word: SKIP
2. If it fits, generate an engineering-grade, objective summary in pure UZBEK language (2-3 sentences maximum).
3. STRICT RULE: DO NOT EXAGGERATE. Avoid hype phrases like "this will change the world forever", "mindblowing", "revolutionary breakthrough", "dunyoni zabt etadi". Keep it strictly factual, professional, and clear.
4. Output only the Uzbek summary or the word SKIP. No introductory or meta-text.

Uzbek Summary (or SKIP):"""

    try:
        response = model.generate_content(prompt)
        return response.text.strip(), sources
    except Exception as e:
        print(f"Gemini tahlil xatoligi: {e}")
        return "SKIP", sources

# ============================================================
# TELEGRAM FORMAT
# ============================================================
def send_to_telegram(summary, sources, links):
    sources_text = ", ".join([s for s in sources])
    main_link = links[0] if links else ""

    message = f"""⚡️ <b>FUTUREX | Robotics & Deep Tech Intelligence</b>

🦾 {summary}

🌐 <b>Global Intel:</b> {sources_text}
🔗 <a href="{main_link}">Tafsilotlar (Manba) →</a>

🤖 <code>[FutureX Engine v2.5 // Autopilot Mode]</code>"""

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    try:
        response = requests.post(url, json=payload)
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Telegramga jo'natishda xatolik: {e}")
        return False

# ============================================================
# ASOSIY ISHGA TUSHIRISH TIZIMI
# ============================================================
def main():
    print(f"\n⚡️ FutureX Core Engine v2.5 yuklanmoqda...")
    
    sent_news = load_sent_news()
    all_news = fetch_all_news()
    
    new_news = [n for n in all_news if n["hash"] not in sent_news]
    print(f"Jami yig'ildi: {len(all_news)} ta xabar. Shulardan yangi: {len(new_news)} ta.")

    if not new_news:
        print("Yangi ma'lumotlar oqimi mavjud emas.")
        return

    groups = group_similar_news(new_news)
    sent_count = 0

    for group in groups[:8]: # Har bir siklda ko'pi bilan 8 ta saralangan post
        try:
            summary, sources = generate_summary_with_gemini(group)
            
            if summary.upper() == "SKIP" or len(summary) < 10:
                for n in group:
                    sent_news.append(n["hash"])
                continue

            links = [n["link"] for n in group]
            if send_to_telegram(summary, sources, links):
                for n in group:
                    sent_news.append(n["hash"])
                sent_count += 1
                print(f"🚀 FutureX kanaliga yangi xabar joylandi!")
                time.sleep(5) # Telegram limitlaridan himoya

        except Exception as e:
            print(f"Blokni qayta ishlashda xatolik: {e}")
            continue

    save_sent_news(sent_news)
    print(f"🤖 Ish yakunlandi. Kanalga {sent_count} ta eng sara muhandislik yangiligi o'zbek tilida chiqarildi.")

if __name__ == "__main__":
    main()
