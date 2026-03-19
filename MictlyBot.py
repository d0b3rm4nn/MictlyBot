import os
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIGURACIÓN ---
TELEGRAM_TOKEN = "7941446061:AAFwRFCpvEA0mufR5ISajsR2U5GQ1aExGGc" # Asegúrate de poner tu token real aquí
FOOTER = "\n\n🤖 **Bot By d0b3rm4nn**"

# --- FUNCIÓN DE CONSULTA (BinList.net) ---
async def bin_checker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Extraer el texto del mensaje
    text = update.message.text
    parts = text.split()
    
    if len(parts) < 2:
        await update.message.reply_text("❌ Uso correcto:\n`.bin 123456` o `/bin 123456`", parse_mode='Markdown')
        return

    bin_num = parts[1].strip()[:8] # Tomamos hasta 8 dígitos que es lo que soporta la API
    
    # Mensaje de espera
    msg_espera = await update.message.reply_text(f"📡 Consultando en **BinList** para: `{bin_num}`...", parse_mode='Markdown')

    url = f"https://lookup.binlist.net/{bin_num}"
    
    # Encabezados para evitar bloqueos
    headers = {
        "Accept-Version": "3",
        "User-Agent": "MictlyBot/1.0"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Extracción de datos con valores por defecto
            bank = data.get('bank', {}).get('name', 'N/A')
            country = data.get('country', {}).get('name', 'N/A')
            emoji = data.get('country', {}).get('emoji', '🌐')
            scheme = data.get('scheme', 'N/A').upper()
            card_type = data.get('type', 'N/A').upper()
            brand = data.get('brand', '')

            res = (
                f"✅ **Resultado BinList**\n"
                f"💳 **BIN:** `{bin_num}`\n"
                f"🏦 **Banco:** `{bank}`\n"
                f"🌍 **País:** {country} {emoji}\n"
                f"📝 **Marca:** {scheme} {brand}\n"
                f"💳 **Tipo:** {card_type}"
            )
        elif response.status_code == 429:
            res = "⚠️ **Límite de API:** Demasiadas consultas en poco tiempo. Espera un minuto."
        else:
            res = f"❌ No se encontró información para el BIN `{bin_num}`."
            
    except Exception as e:
        res = f"⚠️ Error de conexión: {e}"

    # Editamos el mensaje de espera con el resultado final
    await msg_espera.edit_text(res + FOOTER, parse_mode='Markdown')

def main():
    # Inicializar el bot
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Handlers: Responderá a /bin y también a .bin
    app.add_handler(CommandHandler("bin", bin_checker))
    app.add_handler(MessageHandler(filters.Regex(r'^\.bin\s+'), bin_checker))
    
    print("🚀 Bot iniciado: Optimizado solo para BinList.net")
    app.run_polling()

if __name__ == '__main__':
    main()