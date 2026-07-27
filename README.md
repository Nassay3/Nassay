# Nassay

منصة شارت احترافية تعتمد على Binance Global Spot وUSD-M Futures، مع شموع متعددة الأنماط، مؤشرات قابلة للتخصيص، نوافذ سفلية تفاعلية، وحفظ كامل لإعدادات المستخدم.

## التشغيل المباشر

### Windows

```powershell
python run.py
```

### macOS

ثبّت أدوات Apple مرة واحدة:

```bash
xcode-select --install
```

ثم داخل مجلد المشروع:

```bash
python3 run.py
```

يقوم المشغّل بتنزيل نسخة Node خاصة بالمشروع وpnpm عند الحاجة، وتثبيت الحزم، ثم تشغيل:

- الواجهة: `http://localhost:5173`
- API: `http://localhost:5000`

استخدم `python3 run.py --no-sync` على macOS أو `python run.py --no-sync` على Windows لتشغيل النسخة المحلية دون فحص GitHub.

## إعداد جهاز Mac جديد

```bash
xcode-select --install
mkdir -p ~/Developer
cd ~/Developer
git clone https://github.com/Nassay3/Nassay.git
cd Nassay
python3 run.py
```

## المزامنة بين Windows وMac

`main` على GitHub هو المصدر الوحيد للكود. قبل الانتقال إلى جهاز آخر، تأكد أن تعديلات الجهاز الحالي ملتزمة ومرفوعة.

للتأكد يدويًا قبل العمل:

```bash
git status
git pull --ff-only origin main
```

بعد الانتهاء:

```bash
git add -A
git commit -m "Describe the update"
git push origin main
```

لا تنسخ `node_modules` أو `.runtime` بين الأجهزة، ولا تضع أسرار `.env` في Git.

## استمرار سياق Codex

- `AGENTS.md` يحتوي تعليمات العمل الدائمة التي يقرأها Codex من المستودع.
- `PROJECT_STATUS.md` يلخص الحالة الحالية والقرارات والفحوص.
- استخدم حساب OpenAI نفسه على الجهازين.
- للمحادثات التي يجب فتحها على الويب وWindows وMac، استخدم ChatGPT Project مع Cloud Work. محادثات Codex المحلية قد تبقى على الجهاز الذي بدأت منه.

## أوامر التحقق

```bash
pnpm run typecheck
pnpm --filter @workspace/trading-terminal run build
pnpm --filter @workspace/api-server run build
```
