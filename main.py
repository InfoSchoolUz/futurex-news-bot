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
# SOZLAMALAR
# ============================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "@futurex_1984")

# ============================================================
# AI VA TEXNOLOGIYA RSS MANBALAR
# ============================================================
RSS_SOURCES = [
    {"name": "TechCrunch AI",            "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "MIT Technology Review",     "url": "https://www.technologyreview.com/feed/"},
    {"name": "The Verge AI",              "url": "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml"},
    {"name": "VentureBeat AI",            "url": "https://venturebeat.com/category/ai/feed/"},
    {"name": "Wired AI",                  "url": "https://www.wired.com/feed/tag/ai/latest/rss"},
    {"name": "DeepMind Blog",             "url": "https://deepmind.google/blog/rss.xml"},
    {"name": "IEEE Spectrum AI",          "url": "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss"},
    {"name": "Robotics Business Review",  "url": "https://www.roboticsbusinessreview.com/feed/"},
    {"name": "The Robot Report",          "url": "https://www.therobotreport.com/feed/"},
]

SENT_NEWS_FILE = "sent_news.json"
SIMILARITY_THRESHOLD = 0.65

# ============================================================
# YUBORILGAN YANGILIKLAR
# ============================================================
def load_sent_news():
    if os.path.exists(SENT_NEWS_FILE):
        try:
            with open(SENT_NEWS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_sent_news(sent_list):
    with open(SENT_NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(sent_list[-500:], f, ensure_ascii=False)

def get_news_hash(title):
    return hashlib.md5(title.lower().strip().encode("utf-8")).hexdigest()

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
            count = 0
            for entry in feed.entries[:8]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = entry.get("summary", entry.get("description", "")).strip()
                if title and link:
                    all_news.append({
                        "title": title,
                        "link": link,
                        "summary": summary[:600] if summary else "",
                        "source": source["name"],
                        "hash": get_news_hash(title)
                    })
                    count += 1
            print(f"✅ {source['name']}: {count} ta yangilik olindi")
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
# GEMINI AI BILAN XULOSA YARATISH (O'ZBEKCHA)
# ============================================================
def generate_summary_with_gemini(news_group):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.0-flash")

    titles = [n["title"] for n in news_group]
    summaries = [n["summary"] for n in news_group if n["summary"]]
    sources = list(set([n["source"] for n in news_group]))

    prompt = f"""Sen o'zbek tilidagi AI yangiliklari jurnalistisan.
Quyidagi inglizcha yangilikni O'ZBEK TILIDA (lotin alifbosida) yozib ber.

INGLIZCHA SARLAVHA: {titles[0]}
INGLIZCHA MAZMUN: {summaries[0][:400] if summaries else 'Mavjud emas'}

MUHIM QOIDALAR:
- Hamma narsani O'ZBEK TILIDA yoz, birorta inglizcha so'z qoldirma
- Birinchi qatorda: tegishli emoji + o'zbekcha sarlavha
- Ikkinchi qatorda: 2-3 jumlali o'zbekcha tushuntirish
- Oddiy, tushunarli til ishlat
- Texnik atamalarni ham o'zbekchalashtir yoki tushuntir

JAVOB FORMATI (faqat shu ikki qator):
[emoji] [O'zbekcha sarlavha]
[O'zbekcha tushuntirish 2-3 jumla]"""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        # Agar hali ham inglizcha bo'lsa, qayta urinish
        if any(word in text.lower() for word in ["the ", "and ", "of ", "is ", "are "]):
            response2 = model.generate_content(
                f"Quyidagi matnni to'liq O'zbek tiliga (lotin alifbosi) tarjima qil, hech qanday inglizcha so'z qoldirma:\n\n{text}"
            )
            text = response2.text.strip()
        return text, sources
    except Exception as e:
        print(f"Gemini xatolik: {e}")
        return f"🤖 {titles[0]}", sources

# ============================================================
# TELEGRAM GA XABAR YUBORISH
# ============================================================
def send_to_telegram(summary, sources, links):
    lines = summary.strip().split("\n", 1)
    title = lines[0].strip() if lines else summary
    description = lines[1].strip() if len(lines) > 1 else ""

    sources_text = "\n".join([f"• {s}" for s in sources])
    main_link = links[0] if links else ""

    if description:
        message = f"""<b>{title}</b>

{description}

🔗 <b>Manba:</b>
{sources_text}

<a href="{main_link}">Batafsil o'qish →</a>

─────────────────
🚀 <i>FutureX AI News | @futurex_1984</i>"""
    else:
        message = f"""<b>{title}</b>

🔗 <b>Manba:</b>
{sources_text}

<a href="{main_link}">Batafsil o'qish →</a>

─────────────────
🚀 <i>FutureX AI News | @futurex_1984</i>"""

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            print(f"✅ Yuborildi: {title[:60]}...")
            return True
        else:
            print(f"❌ Telegram xatolik ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"❌ Yuborishda xatolik: {e}")
        return False

# ============================================================
# ASOSIY FUNKSIYA
# ============================================================
def main():
    print(f"\n{'='*55}")
    print(f"🚀 FutureX AI News Aggregator")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}\n")

    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY topilmadi!")
        return
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN topilmadi!")
        return

    sent_news = load_sent_news()
    sent_hashes = set(sent_news)

    all_news = fetch_all_news()
    print(f"\n📊 Jami {len(all_news)} ta yangilik olindi")

    new_news = [n for n in all_news if n["hash"] not in sent_hashes]
    print(f"🆕 {len(new_news)} ta yangi yangilik\n")

    if not new_news:
        print("ℹ️ Yangi yangilik yo'q — keyingi tekshiruvda ko'ramiz!")
        return

    groups = group_similar_news(new_news)
    print(f"📦 {len(groups)} ta guruh\n")

    sent_count = 0
    new_hashes = []

    for group in groups[:8]:
        try:
            summary, sources = generate_summary_with_gemini(group)
            links = [n["link"] for n in group]

            if send_to_telegram(summary, sources, links):
                for n in group:
                    new_hashes.append(n["hash"])
                sent_count += 1
                time.sleep(4)
        except Exception as e:
            print(f"❌ Xatolik: {e}")
            continue

    updated = list(sent_hashes) + new_hashes
    save_sent_news(updated)
    print(f"\n{'='*55}")
    print(f"✅ {sent_count} ta yangilik @futurex_1984 ga yuborildi!")
    print(f"{'='*55}\n")

if __name__ == "__main__":
    main()
