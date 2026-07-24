@echo off
REM اجرای یک‌باره: این اسکریپت محیط مجازی را می‌سازد، پکیج‌ها را نصب می‌کند و مایگریشن می‌زند.
REM استفاده: در Command Prompt، داخل پوشه پروژه بنویسید:  setup.bat

echo در حال ساخت محیط مجازی...
python -m venv venv

echo در حال فعال‌سازی و نصب پکیج‌ها...
call venv\Scripts\activate.bat
pip install --upgrade pip -q
pip install -r requirements.txt

echo در حال اجرای مایگریشن...
python manage.py migrate

echo.
echo راه‌اندازی تمام شد.
echo از این به بعد فقط کافیست این دستور را بزنید تا محیط فعال شود:
echo   venv\Scripts\activate
echo سپس پروژه را اجرا کنید:
echo   python manage.py runserver
