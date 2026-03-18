ORZUMALL TELEGRAM BOT — RAILWAY UCHUN TAYYOR PAKET

Ichida bor fayllar:
- bot.py
- requirements.txt
- Procfile
- runtime.txt
- .env.example

RAILWAYGA JOYLASH TARTIBI:
1) GitHub'da yangi repository yarating.
2) Shu papkadagi barcha fayllarni repository ichiga yuklang.
3) Railway -> New Project -> GitHub Repository ni bosing.
4) Repository'ni tanlang.
5) Deploy bo'lgach Variables bo'limiga kiring va quyidagilarni qo'shing:
   BOT_TOKEN=... sizning Telegram bot tokeningiz
   WEB_APP_URL=https://saytingiz.com/ yoki Netlify link
   ADMIN_CHAT_ID=... sizning Telegram raqamli chat ID

Agar Start Command so'rasa:
python bot.py

MUHIM:
- BOT_TOKEN bo'lmasa bot ishlamaydi.
- ADMIN_CHAT_ID noto'g'ri bo'lsa foydalanuvchi xabarlari admin'ga bormaydi.
- Avval botga /start yuborib ko'ring.

GITHUBGA YUKLASHNING ENG OSON YO'LI:
- GitHub repository oching
- Add file -> Upload files
- Shu papkadagi fayllarni tashlang
- Commit qiling

TEST:
1) Railway deploy tugasin
2) Variables saqlansin
3) Logs ichida bot ishga tushganini tekshiring
4) Telegramda botga /start yuboring
