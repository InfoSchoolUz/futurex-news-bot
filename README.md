# 📰 FutureX News Aggregator

O'zbekiston yangilik saytlaridan avtomatik yangilik yig'ib, Telegram kanalga yuboruvchi AI agent.

## ✨ Imkoniyatlar

- 10+ o'zbek yangilik saytidan RSS orqali yangilik oladi
- Bir xil yangilikni birlashtiradi (duplicate yo'q)
- Gemini AI bilan o'zbek tilida xulosa yozadi
- Manbalarni ko'rsatadi
- Har 30 daqiqada avtomatik ishlaydi (GitHub Actions)

## 🚀 O'rnatish

### 1. Repository yaratish
GitHub da yangi repo oching: `futurex-news-bot`

### 2. Fayllarni yuklash
Quyidagi fayllarni repoga yuklang:
- `main.py`
- `requirements.txt`
- `.github/workflows/news_aggregator.yml`

### 3. Secrets qo'shish
GitHub repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret nomi | Qiymati |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio dan olingan API key |
| `TELEGRAM_BOT_TOKEN` | @BotFather dan olingan token |
| `TELEGRAM_CHANNEL_ID` | `@futurex_1984` |

### 4. Gemini API key olish
1. https://aistudio.google.com ga kiring
2. "Get API key" tugmasini bosing
3. Bepul API key oling

### 5. Telegram Bot yaratish
1. @BotFather ga `/newbot` yuboring
2. Bot nomi: `FutureX News Bot`
3. Token oling va Secrets ga qo'shing
4. Botni @futurex_1984 kanalga admin qiling

## 📊 Kanal ko'rinishi

```
📰 Toshkentda yangi metro stansiyasi ochildi

🔗 Manbalar:
• Kun.uz
• Gazeta.uz
• Daryo.uz

Batafsil o'qish →

🤖 FutureX AI News Aggregator
```

## 📡 Manbalar
- Kun.uz
- Gazeta.uz  
- Daryo.uz
- Aniq.uz
- Darakchi.uz
- Nuz.uz
- BBC O'zbek
- Ozodlik
- Uza.uz
- Xs.uz
