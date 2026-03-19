import os
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIGURACIÓN ---
TELEGRAM_TOKEN = "7941446061:AAFwRFCpvEA0mufR5ISajsR2U5GQ1aExGGc"
RAPIDAPI_KEY = "TU_RAPIDAPI_KEY" # Mantén esta si la tienes, o déjala vacía

FOOTER = "\n\n🤖 **Bot Summon By d0b3rm4nn**"

# --- FUNCIÓN PARA BINLIST.NET (Comando .bin) ---
async def bin_list_net(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("❌ Uso: `.bin 123456`", parse_mode='Markdown')
        return

    bin_num = parts[1].strip()[:8] # Binlist acepta hasta 8 dígitos
    await update.message.reply_text(f"📡 Consultando en **BinList** para: `{bin_num}`...", parse_mode='Markdown')

    url = f"https://lookup.binlist.net/{bin_num}"
    
    # Binlist requiere un Header específico para evitar bloqueos
    headers = {
        "Accept-Version": "3",
        "User-Agent": "MictlyBot/1.0"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Extraer datos con seguridad (get)
            bank = data.get('bank', {}).get('name', 'N/A')
            country = data.get('country', {}).get('name', 'N/A')
            emoji = data.get('country', {}).get('emoji', '')
            scheme = data.get('scheme', 'N/A').upper() # Visa, Mastercard, etc.
            card_type = data.get('type', 'N/A').upper() # Debit, Credit
            brand = data.get('brand', 'N/A')

            res = (
                f"✅ **Resultado BinList**\n"
                f"💳 **BIN:** `{bin_num}`\n"
                f"🏦 **Banco:** `{bank}`\n"
                f"🌍 **País:** {country} {emoji}\n"
                f"📝 **Marca:** {scheme} / {brand}\n"
                f"💳 **Tipo:** {card_type}"
            )
        elif response.status_code == 404:
            res = f"❌ No se encontró información para el BIN `{bin_num}`."
        elif response.status_code == 429:
            res = "⚠️ **Límite alcanzado:** Binlist permite pocas consultas por minuto. Intenta de nuevo en un momento."
        else:
            res = f"❌ Error en la API (Código: {response.status_code})"
            
    except Exception as e:
        res = f"⚠️ Error de conexión: {e}"

    await update.message.reply_text(res + FOOTER, parse_mode='Markdown')

# --- FUNCIÓN PARA RAPIDAPI (Comando /bin) ---
async def bin_rapid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Uso: `/bin 123456`", parse_mode='Markdown')
        return
    
    bin_num = context.args[0].strip()[:6]
    await update.message.reply_text(f"🔍 Consultando en **RapidAPI** para: `{bin_num}`...", parse_mode='Markdown')

    url = f"https://bin-check-api.p.rapidapi.com/bin/{bin_num}"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "bin-check-api.p.rapidapi.com"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()

        if response.status_code == 200 and data.get('success'):
            res = (
                f"✅ **Resultado RapidAPI**\n"
                f"💳 **BIN:** `{bin_num}`\n"
                f"🏦 **Banco:** {data.get('bank', 'N/A')}\n"
                f"🌍 **País:** {data.get('country', 'N/A')}\n"
                f"📝 **Tipo:** {data.get('type', 'N/A')}"
            )
        else:
            res = f"❌ RapidAPI: {data.get('message', 'Sin datos.')}"
    except Exception as e:
        res = f"⚠️ Error: {e}"

    await update.message.reply_text(res + FOOTER, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 **MictlyBot Online**\n\n`.bin` -> BinList (Free)\n`/bin` -> RapidAPI" + FOOTER, parse_mode='Markdown')

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bin", bin_rapid))
    app.add_handler(MessageHandler(filters.Regex(r'^\.bin\s+'), bin_list_net))
    
    print("🚀 Bot iniciado con BinList.net configurado.")
    app.run_polling()

if __name__ == '__main__':
    main()