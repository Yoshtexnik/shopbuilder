# ShopBuilder: Telegram do'kon konstruktori + kafe boti

Bitta Django loyihasi: har bir sotuvchi o'z botini ulaydi, menyuni admin panelda to'ldiradi, buyurtmalar
do'konning Telegram guruhiga tushadi. Birinchi shablon: **kafe/fastfood** (ish vaqti, minimal summa, masofa
bo'yicha yetkazish narxi, kuryer). Stek: Python 3.12, Django 5, aiogram 3, PostgreSQL, Redis (ixtiyoriy).

## 1. Ishga tushirish (Docker'siz)

### A) Kompyuterda sinash (SQLite, 5 daqiqa)
```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # Windows: copy .env.example .env
```
`.env` da: `DEBUG=1`, `ALLOWED_HOSTS=*`, `SECRET_KEY=istalgan-uzun-qator`, `POSTGRES_DB=` bo'sh (SQLite).
Telegram webhook uchun HTTPS kerak, shuning uchun tunnel oching (alohida terminalda):
```bash
cloudflared tunnel --url http://localhost:8000     # chiqqan https://....trycloudflare.com manzilini oling
```
Shu manzilni `.env` dagi `BASE_URL` ga yozing, keyin:
```bash
python manage.py migrate
python manage.py createsuperuser
uvicorn config.asgi:application --port 8000 --reload
```
`manage.py runserver` ishlatmang: bot webhook'i async, uvicorn kerak. Tunnel manzili har safar o'zgaradi;
o'zgarsa `BASE_URL` ni yangilab, `python manage.py set_webhooks` ni bajaring.

### B) Serverda (Ubuntu 22.04/24.04, domen bilan)
```bash
sudo apt update && sudo apt install -y python3-venv postgresql redis-server git
sudo -u postgres createuser shopbuilder -P
sudo -u postgres createdb shopbuilder -O shopbuilder
sudo adduser --system --group --home /opt/shopbuilder shopbuilder
sudo -u shopbuilder git clone <repo-url> /opt/shopbuilder
cd /opt/shopbuilder
sudo -u shopbuilder python3 -m venv venv
sudo -u shopbuilder venv/bin/pip install -r requirements.txt
sudo -u shopbuilder cp .env.example .env && sudo -u shopbuilder nano .env
```
`.env`: `DEBUG=0`, `SECRET_KEY`, `BASE_URL=https://domeningiz`, `ALLOWED_HOSTS=domeningiz`, `FIELD_ENCRYPTION_KEY`,
`POSTGRES_DB=shopbuilder`, `POSTGRES_PASSWORD=...`, `REDIS_URL=redis://localhost:6379/0`.
```bash
sudo -u shopbuilder venv/bin/python manage.py migrate
sudo -u shopbuilder venv/bin/python manage.py collectstatic --noinput
sudo -u shopbuilder venv/bin/python manage.py createsuperuser
sudo cp deploy/shopbuilder.service /etc/systemd/system/
sudo systemctl enable --now shopbuilder
```
HTTPS uchun Caddy: `sudo apt install -y caddy`, `deploy/Caddyfile` ni `/etc/caddy/Caddyfile` ga ko'chiring,
domenni yozing, `sudo systemctl reload caddy`. Obuna eslatmalari uchun `crontab -e` (shopbuilder foydalanuvchisida):
```
0 9 * * * cd /opt/shopbuilder && venv/bin/python manage.py notify_expiring
```
Yangilash: `git pull && venv/bin/pip install -r requirements.txt && venv/bin/python manage.py migrate &&
venv/bin/python manage.py collectstatic --noinput && sudo systemctl restart shopbuilder`.

> `FIELD_ENCRYPTION_KEY` ni zaxiralang. Bot tokenlari va to'lov kalitlari bazada shu kalit bilan shifrlangan;
> yo'qolsa ularni qayta kiritishga to'g'ri keladi.

## 2. Birinchi kafeni ulash

1. @BotFather'da bot yarating, tokenni oling.
2. Admin → **Do'konlar → qo'shish**: shablon «Kafe», bot tokenini kiriting. Saqlaganda webhook **avtomatik** o'rnatiladi
   (xabar yuqorida chiqadi). Domen o'zgarsa: `python manage.py set_webhooks`.
3. Buyurtmalar guruhi: Telegram guruh yarating, botni qo'shing, guruhga `/chatid` yozing, chiqqan raqamni
   «Buyurtmalar guruhi ID» maydoniga kiriting.
4. **Kategoriyalar** va **Mahsulotlar** qo'shing. **Kafe sozlamalari**: ish vaqti, minimal summa, yetkazish narxi,
   har km narxi, oshxona koordinatalari (Google Maps'dan), maksimal masofa.
5. Kuryer kerak bo'lsa: **Kuryerlar**. Kuryer botga `/start` yozadi, `/chatid` bergan «Sizning ID» ni kiriting.
   «Yo'lga chiqdi» bosilganda eng kam band kuryerga buyurtma va lokatsiya yuboriladi.

## 3. Konstruktor: boshqa sotuvchilar

```bash
python manage.py create_seller ali --password 'KuchliParol1'
```
Sotuvchi admin panelga kirib, o'z do'konini o'zi qo'shadi va **faqat o'z ma'lumotlarini** ko'radi. Tarif va
obuna sanasini faqat superuser o'zgartiradi (yangi do'kon `TRIAL_DAYS` kunlik sinov bilan boshlanadi).
Do'konlar ro'yxatida «Obunani 30 kunga uzaytirish» amali bor. Obuna tugasa bot «buyurtma qabul qilmayapti» deydi.
Tarif (Plan) mahsulotlar sonini cheklaydi.

## 4. Click va Payme

Do'kon sozlamalarida har sotuvchi o'z kalitlarini kiritadi. Click/Payme kabinetida manzillar:

| Provayder | URL |
|---|---|
| Click (Prepare va Complete) | `https://<DOMAIN>/pay/click/<do'kon ID>/` |
| Payme (Merchant API) | `https://<DOMAIN>/pay/payme/<do'kon ID>/` |

Buyurtma raqami (`order.id`) Click'da `merchant_trans_id`, Payme'da `account.order_id`. Summa serverda qayta
hisoblanadi; imzo/Basic-auth tekshiriladi.

## 5. Mini App

`https://<DOMAIN>/app/<do'kon ID>/`. Bot asosiy menyusida «🌐 Mini App» tugmasi chiqadi. Buyurtma Telegram `initData`
imzosi bilan tasdiqlanadi (soxta so'rov o'tmaydi), narxlar doim bazadan olinadi.

## 6. Tuzilma

```
config/        settings, urls, asgi
apps/shops     Shop, Plan, shifrlangan maydonlar, webhook o'rnatish, admin, buyruqlar
apps/catalog   Category, Product
apps/orders    Customer, Order, OrderItem + servislar (narx hisobi, holatlar)
apps/payments  Click va Payme
apps/cafe      CafeSettings, Courier, yetkazish narxi
bot/           aiogram: loader (bitta Dispatcher, ko'p bot), webhook, handlerlar, flows
webapp/        Mini App (HTML/JS) va API
tests/         21 ta test
```

## 7. Testlar

```bash
DEBUG=1 python manage.py test tests
```
Bot oqimi soxta Telegram sessiyasi bilan, to'lovlar Click/Payme protokoli bo'yicha tekshiriladi.

## 8. Hali tekshirilmagan narsalar (ishga tushirishdan oldin)

- PostgreSQL bilan sinab ko'rilmagan (testlar SQLite'da). Kod standart Django ORM, lekin birinchi marta serverga
  qo'ygandan keyin buyurtma berib ko'ring.
- Haqiqiy Telegram, Click va Payme sandbox bilan sinalmagan. Payme'ning rasmiy sinov paneli (test.paycom.uz) va
  Click test rejimidan o'tkazing.
- Mini App brauzerda/Telegram'da vizual tekshirilmagan.
- Mahsulot rasmlari `/media/` orqali Caddy'dan beriladi (deploy/Caddyfile da sozlangan).
