# MictlyBot

Bot de Telegram para consultar **metadatos públicos de un BIN** (prefijo de 6 a 8
dígitos) usando [BinList](https://lookup.binlist.net/): banco, país, marca, tipo y
si es prepaga. Incluye validación del dígito de control (Luhn), caché persistente
en SQLite y límite de peticiones por usuario.

> Solo trabaja con **metadatos públicos de un prefijo**. No almacena ni procesa
> números de tarjeta completos; `/luhn` únicamente comprueba el dígito de control.

## Requisitos

- Python 3.10+
- Un token de bot de [@BotFather](https://t.me/BotFather)

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # o: pip install -e ".[dev]"
```

## Configuración

Copia `.env.example` a `.env` y rellena el token:

```bash
cp .env.example .env
```

```dotenv
TELEGRAM_TOKEN=123456:ABC...        # obligatorio
# Opcionales
# BINLIST_USER_AGENT=MictlyBot/1.0
# CACHE_TTL_SECONDS=86400           # 24 h
# RATE_LIMIT_PER_MINUTE=5
# CACHE_DB_PATH=bins_cache.db
# STRIPE_SECRET_KEY=sk_test_...     # solo para tools/stripe_probe.py
```

`.env` está en `.gitignore`: **nunca** se sube al repositorio.

## Uso

```bash
python -m mictlybot
```

### Comandos en Telegram

| Comando | Descripción |
|---|---|
| `/bin <6-8 dígitos>` | Busca banco, país, marca y tipo del BIN |
| `/luhn <número>` | Valida el dígito de control (no almacena el número) |
| `/start` | Mensaje de bienvenida |
| `/help` | Ayuda |

Atajo sin slash: `.bin 45717360`.

## Arquitectura

```
mictlybot/
├── app.py            # construcción y arranque de la Application
├── handlers.py       # handlers de Telegram (/bin, /luhn, /start, /help)
├── commands.py       # registro de comandos en el menú de Telegram
├── binlist.py        # cliente asíncrono de lookup.binlist.net + normalización
├── formatter.py      # formato Markdown de la respuesta
├── cache.py          # caché TTL en memoria (alternativa)
├── sqlite_cache.py   # caché persistente SQLite (por defecto)
├── ratelimit.py      # límite de peticiones por usuario
├── luhn.py           # validación del dígito de control
└── config.py         # configuración desde el entorno (.env)
```

## Tests y lint

```bash
pytest          # 62 tests
ruff check .
```

## Herramientas

`tools/stripe_probe.py` es una sonda de **Stripe en modo test (sandbox)** que
explora los namespaces `/v1` y `/v2`, compara versiones de API (`Stripe-Version`)
y muestra `status`, `decline_code` y errores usando *PaymentMethods* de prueba.
No usa tarjetas ni claves reales (rechaza cualquier clave que no sea `sk_test_`).

```bash
export STRIPE_SECRET_KEY=sk_test_...
python tools/stripe_probe.py            # v1: matriz de PaymentMethods
python tools/stripe_probe.py --versions # compara Stripe-Version
python tools/stripe_probe.py --v2       # namespace /v2
python tools/stripe_probe.py --all      # todo
```

## Despliegue

El bot usa **polling** y una caché **SQLite persistente**, así que necesita un
proceso siempre encendido con disco persistente:

- **VPS** (p. ej. Oracle Cloud Free Tier) — ejecuta `python -m mictlybot` con
  `systemd` o dentro de una sesión `tmux`/`screen`.
- **Termux (Android)** — mismo comando, si dejas el dispositivo encendido.

Las PaaS que suspenden procesos por inactividad (Render, Koyeb...) requieren
cambiar a **webhooks** y un volumen persistente.

## Licencia

Uso educativo y de consulta. Los datos provienen de BinList, una fuente pública.
