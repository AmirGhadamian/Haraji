#!/usr/bin/env bash
# اجرای یک‌باره: این اسکریپت محیط مجازی را می‌سازد، پکیج‌ها را نصب می‌کند و مایگریشن می‌زند.
# استفاده: در ترمینال، داخل پوشه پروژه بنویسید:  bash setup.sh

set -e

echo "در حال ساخت محیط مجازی..."
python3 -m venv venv

echo "در حال فعال‌سازی و نصب پکیج‌ها..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt

echo "در حال اجرای مایگریشن..."
python manage.py migrate

echo ""
echo "✅ راه‌اندازی تمام شد."
echo "از این به بعد فقط کافیست این دستور را بزنید تا محیط فعال شود:"
echo "  source venv/bin/activate"
echo "سپس پروژه را اجرا کنید:"
echo "  python manage.py runserver"
