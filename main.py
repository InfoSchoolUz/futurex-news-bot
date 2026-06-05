import feedparser
import google.generativeai as genai
import requests
import json
import os
import hashlib
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher

# ============================================================
# SOZLAMALAR - bularni o'zingizning ma'lumotlaringiz bilan almashtiring
# ============================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "@futurex_1984")

# ============================================================
# RSS MANBALAR
# ============================================================
RSS_SOURCES = [
    {"name": "Kun.uz",        "url": "https://kun.uz/rss"},
    {"name": "Gazeta.uz",     "url": "https://www.gazeta.uz/rss/"},
    {"name": "Daryo.uz",      "url": "https://daryo.uz/feed"},
    {"name": "Aniq.uz",       "url": "https://aniq.uz/rss"},
    {"name": "Darakchi.uz",   "url": "https://darakchi.uz/rss"},
    {"name": "Nuz.uz",        "url": "https://nuz.uz/feed"},
    {"name": "BBC O'zbek",    "url": "https://feeds.bbci.co.uk/uzbek/rss.xml"},
    {"name": "Ozodlik",       "url": "https://www.ozodlik.org/api/zfpjlvem"},
    {"name": "Uza.uz",        "url": "https://uza.uz/rss"},
    {"name": "Xs.uz",         "url": "https://xs.uz/rss"},
]

SENT_NEWS_FILE = "sent_news.json"
SIMILARITY_THRESHOLD = 0.65  # 65% o'xshash bo'lsa bir xil yangilik deb hisoblanadi

# ============================================================
# YUBORILGAN YANGILIKLAR - DUPLICATE OLDINI OLISH
# ============================================================
def load_sent_news():
    if os.path.exists(SENT_NEWS_FILE):
        with open(SENT_NEWS_FILE, "r") as f:
            return json.load(f)
    return []

def save_sent_news(sent_list):
    # Faqat so'nggi 500 ta yangilikni saqlaydi
    with open(SENT_NEWS_FILE, "w") as f:
        json.dump(sent_list[-500:], f)

def get_news_hash(title):
    return hashlib.md5(title.lower().strip().encode()).hexdigest()

def is_similar(title1, title2):
    return SequenceMatcher(None, title1.lower(), title2.lower()).ratio() > SIMILARITY_THRESHOLD

# ============================================================
# RSS DAN YANGILIKLAR O'QISH
# ============================================================
def fetch_all_news():
    all_news = []
    for source in RSS_SOURCES:
        try:
            feed = feedparser.parse(source["url"])
            for entry in feed.entries[:10]:  # Har manbadan max 10 ta
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = entry.get("summary", entry.get("description", "")).strip()
                if title and link:
                    all_news.append({
                        "title": title,
                        "link": link,
                        "summary": summary[:500] if summary else "",
                        "source": source["name"],
                        "hash": get_news_hash(title)
                    })
            print(f"✅ {source['name']}: {len(feed.entries)} yangilik olindi")
        except Exception as e:
            print(f"❌ {source['name']} xatolik: {e}")
    return all_news

# ============================================================
# BIR XIL YANGILIKLARNI BIRLASHTIRISH
# ============================================================
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
# GEMINI AI BILAN XULOSA YARATISH
# ============================================================
def generate_summary_with_gemini(news_group):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.0-flash")

    titles = [n["title"] for n in news_group]
    summaries = [n["summary"] for n in news_group if n["summary"]]
    sources = list(set([n["source"] for n in news_group]))

    prompt = f"""Quyidagi bir xil voqea haqidagi yangiliklar turli o'zbek saytlaridan olingan.
    
Sarlavhalar:
{chr(10).join(f'- {t}' for t in titles)}

Qisqacha mazmunlar:
{chr(10).join(f'- {s}' for s in summaries[:3])}

Vazifang:
1. O'zbek tilida qisqa va aniq 2-3 jumlali xulosa yoz
2. Eng muhim faktlarni ajratib ko'rsat
3. Neytral va professional til ishlat
4. Faqat xulosa matnini yoz, boshqa hech narsa yozma

Xulosa:"""

    try:
        response = model.generate_content(prompt)
        return response.text.strip(), sources
    except Exception as e:
        print(f"Gemini xatolik: {e}")
        # Gemini ishlamasa ham asosiy sarlavhani qaytaradi
        return titles[0], sources

# ============================================================
# TELEGRAM GA XABAR YUBORISH
# ============================================================
def send_to_telegram(summary, sources, links):
    sources_text = "\n".join([f"• {s}" for s in sources])
    
    # Asosiy link (birinchi manba)
    main_link = links[0] if links else ""

    message = f"""📰 <b>{summary}</b>

🔗 <b>Manbalar:</b>
{sources_text}

<a href="{main_link}">Batafsil o'qish →</a>

🤖 <i>FutureX AI News Aggregator</i>"""

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print(f"✅ Telegram ga yuborildi: {summary[:50]}...")
            return True
        else:
            print(f"❌ Telegram xatolik: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Telegram yuborishda xatolik: {e}")
        return False

# ============================================================
# ASOSIY FUNKSIYA
# ============================================================
def main():
    print(f"\n{'='*50}")
    print(f"🚀 FutureX News Aggregator ishga tushdi")
    print(f"⏰ Vaqt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    # Yuborilgan yangiliklar ro'yxatini yuklash
    sent_news = load_sent_news()
    sent_hashes = set(sent_news)

    # Barcha manbalardan yangilik olish
    all_news = fetch_all_news()
    print(f"\n📊 Jami {len(all_news)} ta yangilik olindi\n")

    # Yangi (yuborilmagan) yangiliklar
    new_news = [n for n in all_news if n["hash"] not in sent_hashes]
    print(f"🆕 {len(new_news)} ta yangi yangilik topildi\n")

    if not new_news:
        print("ℹ️ Yangi yangilik yo'q")
        return

    # Bir xil yangiliklarni birlashtirish
    groups = group_similar_news(new_news)
    print(f"📦 {len(groups)} ta guruh yaratildi\n")

    sent_count = 0
    for group in groups[:10]:  # Bir ishga tushishda max 10 ta yangilik
        try:
            # AI bilan xulosa yaratish
            summary, sources = generate_summary_with_gemini(group)
            links = [n["link"] for n in group]

            # Telegram ga yuborish
            if send_to_telegram(summary, sources, links):
                # Yuborilgan yangiliklar ro'yxatini yangilash
                for n in group:
                    sent_hashes.add(n["hash"])
                    sent_news.append(n["hash"])
                sent_count += 1
                time.sleep(3)  # Spam oldini olish uchun 3 soniya kutish

        except Exception as e:
            print(f"❌ Xatolik: {e}")
            continue

    # Saqlash
    save_sent_news(list(sent_hashes))
    print(f"\n✅ Jami {sent_count} ta yangilik yuborildi!")

if __name__ == "__main__":
    main()