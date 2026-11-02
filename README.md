# Shaxsiy 29-avtobus Telegram monitoringi

Ikki Docker konteyneri: `bot` (Telegram polling, faqat siz uchun) va `monitor` (Xvfb + grafik Chromium + Playwright). Bitta Yandex Maps bekati tayyor. Har bir bekatda kuzatiladigan avtobuslar va keyingi bekatlar `stops.json` orqali belgilanadi.

## Qanday ishlaydi?

1. Telegram'da `/start` yuborasiz, **inline** bekat tugmalari paydo bo‘ladi.
2. Bekatni bosganingizda `monitor` konteynerida grafik Chromium ishga tushadi. Host serverga Xvfb o‘rnatish shart emas.
3. Yandex Maps bekat sahifasi har **30 soniyada** bir marta ochiladi va `stops.json` dagi barcha tanlangan avtobuslarning ETA qiymatlari ajratiladi. `bot` esa **60 soniyada** bir marta avvalgi bildirishnomani o‘chirib, har bir avtobus natijasi yozilgan yangi xabar yuboradi. Xabar ichida ham **To‘xtatish** tugmasi bor.
4. ETA bo‘lmasa: «ETA hozircha mavjud emas». CAPTCHA/limited bo‘lsa: tegishli xato; 5 daqiqa tanaffus. Brauzer xatosida avtomatik qayta ochishga urinish.
5. Stop bosilsa Chromium yopiladi. Agar bot qayta ishga tushsa, kuzatuv avtomatik tiklanmaydi.

## Talablar

- Linux x86-64 host, Docker Engine + Docker Compose v2, internetga chiqish.
- Tekshirilgan xost: 4 vCPU, 7.6 GiB RAM. `monitor` uchun **2 GiB / 1.5 CPU**, `bot` uchun **256 MiB / 0.35 CPU** limit qo‘yilgan. `monitor` uchun `/dev/shm` = 512 MiB.
- Resurs limitlari sizning dastlabki Chromium PSS ≈591 MiB natijangizga asoslangan boshlang‘ich limitlar, uzoq muddatli Docker o‘lchovi emas.

## Ishga tushirish (Ubuntu)

```bash
cd ~/bus-telegram-docker
cp .env.example .env
nano .env
```

`.env` ichida uchta qiymatni to‘ldiring:

- `TELEGRAM_BOT_TOKEN` — Telegram @BotFather yaratgan bot tokeni.
- `TELEGRAM_ALLOWED_USER_ID` — sizning **raqamli** Telegram ID'ingiz (masalan @userinfobot orqali).
- `MONITOR_API_KEY` — har bir o‘rnatishda alohida random kalit. Generatsiya:

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
chmod 600 .env
mkdir -p debug
```

Dastlab **Docker ichida Xvfb ishlashini tekshiring**. Host'dagi Xvfb'ni hozircha olib tashlamang:

```bash
docker compose build
docker compose run --rm --no-deps --entrypoint xvfb-run monitor \
  -a -s '-screen 0 1920x1080x24' python -m monitor.check_once
```

Kutilgan: `status=ok` va tanlangan avtobuslar uchun ETA yoki `status=no_eta` (hech birida prognoz yo‘q paytida). `status=limited`, `captcha` yoki `wrong_page` bo‘lsa, `debug/` loglarini tekshiring. Bir martalik muvaffaqiyat yetarli emas; botni 30–60 daqiqa sinang.

Keyin:

```bash
docker compose config --quiet
docker compose up -d
docker compose ps
docker compose logs --tail=60 -f bot monitor
```

Telegram'da botga `/start` yuboring va bekatni tanlang. Monitoringni to‘xtatish uchun menyudan yoki kelayotgan bildirishnomadan **⏹** tugmasini bosing.

Resurslarni kuzatish:

```bash
docker stats personal-bus-monitor-bot-1 personal-bus-monitor-monitor-1
```

Konteyner nomlari boshqacha bo‘lsa, `docker compose ps` orqali aniqlang yoki `docker stats` deb ko‘ring.

## Nima uchun inline tugmalar?

Inline tugmalar **har bir bekatga alohida Start/Stop** biriktirish, aktiv bekatni menyuda Stop holatiga o‘tkazish va yangi ETA xabarining o‘ziga ham Stop tugmasini qo‘yish imkonini beradi. Reply klaviatura chat ostida doimiy joy egallaydi; u bilan bekatlar holatini shu darajada qulay ko‘rsatish qiyinroq.

**Eslatma:** menyu xabarining tugmalari `edit_message_reply_markup` orqali yangilanadi, lekin **ETA xabari hech qachon tahrirlanmaydi**. Har 60 soniyada eski ETA xabari o‘chirilib, **yangi Telegram xabari** yuboriladi. Chat bildirishnomalari sozlamalari ovozsiz bo‘lsa, yangi xabar ham ovozli signal bermasligi mumkin.

## Yangi bekat qo‘shish

`stops.json` dagi har bir bekatda `id` (unikal slug), `stop_id`, `label`, `page_stop_name` (Yandex sahifasidagi aynan ruscha bekat nomi), `url` va bo‘sh bo‘lmagan `buses` ro‘yxati bo‘lishi kerak. Har bir avtobusda `route` (raqam), `destination` (sahifada ko‘rinadigan ruscha yo‘nalish) va `direction_label` (Telegramda ko‘rsatiladigan nom) talab qilinadi. Masalan, mavjud bekatga yana bir avtobus qo‘shish uchun:

```json
"buses": [
  {"route": "29", "destination": "Пахтакор", "direction_label": "Metro Paxtakor"},
  {"route": "72", "destination": "Чорсу", "direction_label": "Chorsu"}
]
```

Ikkinchi yozuv misol: raqam va yo‘nalishni Yandex sahifasida aynan ko‘rsatilgan qiymatlarga almashtiring. Bir bekat ichida bir xil `route` va `destination` juftligi takrorlanmaydi. Oldingi bitta avtobusli (`route`, `destination`, `direction_label` bevosita bekat ichida) format ham qabul qilinadi.

Yangi bekatlar uchun **parsingni alohida tekshiring**: Yandex sahifalarining tuzilmasi o‘zgarishi mumkin.

```bash
docker compose up -d --build
```

Standart `MAX_ACTIVE_STOPS=1`, ya'ni hozircha bir vaqtning o‘zida faqat bitta bekat ishlaydi; shu bekatdagi bir nechta avtobus bir Chromium sessiyasida kuzatiladi. Bir nechta bekatni parallel kuzatmoqchi bo‘lsangiz `compose.yaml` da `MAX_ACTIVE_STOPS` ni 2 yoki 3 ga ko‘taring va monitor RAM limitini qo‘shimcha Chromium jarayonlari uchun oshiring. **Har bir aktiv bekat alohida Chromium ishlatadi.**

## Diagnostika va xatolar

```bash
docker compose logs -f monitor
docker compose logs -f bot
ls -lh debug/
```

`limited` yoki CAPTCHA holatida monitor bir necha daqiqa kutadi, tez-tez qayta urinmaydi. Debug fayllarda sahifa skrinshoti va ekranda ko‘rinadigan matn bo‘ladi; ularni ommaga ulashishdan oldin tekshiring. Ichki Yandex URL tokenlari faylga saqlanmaydi.

Agar monitor konteyneri o‘chib, qayta ochilsa, Telegram bot «monitor kutilmaganda to‘xtagan» deb yangi xabar yuboradi va bekat tugmasini yana Start holatiga qaytaradi. Faqat siz qayta Start bosganingizdagina yangi kuzatuv boshlanadi.

Agar Stop paytida bot monitorga ulana olmasa, Telegram xabarlari to‘xtaydi, ammo serverdagi kuzatuvni to‘xtatishni kafolatlab bo‘lmaydi. Bunday holatda `docker compose restart monitor` bilan eski sessiyani tozalash mumkin.

## Host Xvfb'ni olib tashlash

Faqat Docker ichidagi **headed** sinov va davomli monitoring muvaffaqiyatli o‘tgandan keyin, va host'dagi boshqa xizmatlar bu paketlardan foydalanmasligiga ishonch hosil qilib:

```bash
sudo apt purge xvfb xauth
```

`autoremove` ni serverdagi boshqa paketlar ro‘yxatini tekshirmasdan ishga tushirmang. Docker konteynerdagi Xvfb host paketlariga bog‘liq emas.

## Docker ichidagi Xvfb ishlamasa: host rejimi

Agar Docker konteynerining **headed** testi doimiy `limited` qaytarsa, host'dagi avval ishlagan Xvfb konfiguratsiyasiga qaytishingiz mumkin. Bunday holda **host Xvfb paketlarini olib tashlamang**. Ikkala xizmatni host'da ikkita terminalda sinab ko‘ring:

```bash
cd ~/bus-telegram-docker
python3 -m venv .venv
source .venv/bin/activate
pip install -r monitor/requirements.txt -r bot/requirements.txt
python -m playwright install --with-deps chromium
set -a; source .env; set +a
export STOPS_FILE="$PWD/stops.json"
export DEBUG_DIR="$PWD/debug"
xvfb-run -a -s '-screen 0 1920x1080x24' \
  uvicorn monitor.app:app --host 127.0.0.1 --port 8099
```

Ikkinchi terminalda:

```bash
cd ~/bus-telegram-docker
source .venv/bin/activate
set -a; source .env; set +a
export STOPS_FILE="$PWD/stops.json"
export MONITOR_URL=http://127.0.0.1:8099
python -m bot.app
```

Bu zaxira variantda monitor API faqat `127.0.0.1` da tinglaydi. Doimiy xizmatga o‘tkazishda ikkita `systemd` unit va resurs chegaralari (`MemoryMax`, `CPUQuota`) kerak bo‘ladi.

## Xavfsizlik

- `.env` faylini Git'ga qo‘shmang; bot tokeni oshkor bo‘lsa @BotFather orqali yangilang.
- Telegram komandalarini faqat `TELEGRAM_ALLOWED_USER_ID` va private chat qabul qiladi.
- Ichki monitor porti **host'ga ochilmagan**; faqat Compose tarmog‘ida ishlaydi va qo‘shimcha `MONITOR_API_KEY` talab qiladi.
- Bot `long polling` bilan ishlaydi; ochiq port, domen va TLS sertifikat talab qilmaydi.
- Yandex sahifasi o‘zgarishi, cheklovlar yoki CAPTCHA tufayli xizmat uzilishi mumkin. Cheklov paytida bot sizga xabar beradi.
