#!/usr/bin/env bash
set -uo pipefail
echo "== pwd =="; pwd
echo "== git toplevel =="; git rev-parse --show-toplevel 2>/dev/null || echo "(no es repo git)"
echo "== remoto =="; git remote -v 2>/dev/null | head -1
echo "== archivos clave =="
for f in pyproject.toml requirements.txt targets.toml mictlybot/cardcheck.py mictlybot/app.py mictlybot/handlers.py mictlybot/config.py; do
  if [[ -f "$f" ]]; then echo "OK    $f"; else echo "FALTA $f"; fi
done
echo "== estado OTP =="
[[ -d mictlybot/otp ]] && echo "otp/ ya existe" || echo "otp/ no existe (limpio)"
grep -c 'OTP_MODE' mictlybot/config.py 2>/dev/null | sed 's/^/OTP_MODE en config.py: /'
echo "== ancla 1: catch-all en cardcheck.py =="
grep -nF "('\"object\": \"payment_method\", \"info\", \"CCN LIVE\")," mictlybot/cardcheck.py || echo "NO ENCONTRADA"
echo "== ancla 2: handler .check en app.py =="
grep -nF "app.add_handler(MessageHandler(filters.Regex(r\"^\.check\s+\"), check_cmd))" mictlybot/app.py || echo "NO ENCONTRADA"
echo "== ancla 3: import de luhn en handlers.py =="
grep -nF "from .luhn import check_card" mictlybot/handlers.py || echo "NO ENCONTRADA"
echo "== ancla 4: bot_data footer en app.py =="
grep -nF 'app.bot_data["footer"] = config.footer' mictlybot/app.py || echo "NO ENCONTRADA"
echo "== ancla 5: import logging en handlers.py =="
grep -nF "import logging" mictlybot/handlers.py || echo "NO ENCONTRADA"
echo "== fin =="
