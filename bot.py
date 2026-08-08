import asyncio

# Python 3.14 Event Loop Fix
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import os
import sys
import logging
import urllib.parse
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

# ==================== CONFIGURATION ====================
API_ID = int(os.environ.get("API_ID", "34305725"))
API_HASH = os.environ.get("API_HASH", "a7439c105c050b5011a90bda4f0e1e90")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8899747292:AAGusFkBrquTmi2gA2DDEm_4f9Woh3Q5XQQ")

WEBSITE_URL = os.environ.get("WEBSITE_URL", "https://hrry.online")
PORT = int(os.environ.get("PORT", "8080"))

raw_stream_url = os.environ.get("STREAM_SERVER_URL", "http://localhost:8080")
if not raw_stream_url.startswith(("http://", "https://")):
    STREAM_SERVER_URL = f"https://{raw_stream_url}"
else:
    STREAM_SERVER_URL = raw_stream_url
# =======================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

app = Client(
    "HrryStreamBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

routes = web.RouteTableDef()

@routes.options("/stream/{chat_id}/{message_id}")
async def options_handler(request):
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Type, Accept",
        }
    )

@routes.get("/")
async def root_handler(request):
    return web.json_response({
        "status": "online",
        "service": "Hrry.online Direct Stream Engine",
        "target_website": WEBSITE_URL
    })

@routes.get("/stream/{chat_id}/{message_id}")
async def stream_handler(request):
    try:
        chat_id = int(request.match_info["chat_id"])
        msg_id = int(request.match_info["message_id"])
        
        message = await app.get_messages(chat_id, msg_id)
        
        if not message or not (message.video or message.document or message.audio):
            return web.Response(status=404, text="Media File Not Found")

        media = message.video or message.document or message.audio
        file_size = media.file_size
        mime_type = getattr(media, "mime_type", "video/mp4") or "video/mp4"

        range_header = request.headers.get("Range")
        from_bytes = 0
        to_bytes = file_size - 1

        if range_header:
            try:
                parts = range_header.replace("bytes=", "").split("-")
                from_bytes = int(parts[0])
                if len(parts) > 1 and parts[1]:
                    to_bytes = int(parts[1])
            except Exception:
                pass

        if from_bytes >= file_size:
            return web.Response(status=416, text="Requested Range Not Satisfiable")

        length = (to_bytes - from_bytes) + 1
        headers = {
            "Content-Type": mime_type,
            "Content-Range": f"bytes {from_bytes}-{to_bytes}/{file_size}",
            "Content-Length": str(length),
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Type, Accept",
        }

        status_code = 206 if range_header else 200
        response = web.StreamResponse(status=status_code, headers=headers)
        await response.prepare(request)

        CHUNK_SIZE = 1024 * 1024
        start_chunk = from_bytes // CHUNK_SIZE
        skip_first_bytes = from_bytes % CHUNK_SIZE

        sent_bytes = 0
        first_chunk = True

        async for chunk in app.stream_media(message, offset=start_chunk):
            if first_chunk:
                chunk = chunk[skip_first_bytes:]
                first_chunk = False

            if not chunk:
                continue

            if sent_bytes + len(chunk) > length:
                chunk = chunk[:length - sent_bytes]

            try:
                await response.write(chunk)
                sent_bytes += len(chunk)
            except Exception:
                break

            if sent_bytes >= length:
                break

        try:
            await response.write_eof()
        except Exception:
            pass

        return response

    except Exception as e:
        logging.error(f"Streaming Error: {e}")
        return web.Response(status=500, text=f"Streaming Error: {str(e)}")

@app.on_message(filters.command("start") & filters.private)
async def start_msg(client, message):
    text = (
        f"✨ **Welcome to Premium Cloud Player!**\n\n"
        f"🛡 **How to use:**\n"
        f"Just forward or send me any **Video** or **Document** file here.\n"
        f"⚡ I will instantly generate a high-speed streaming and download link for you."
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Visit Hrry.online", url=WEBSITE_URL)]
    ])
    await message.reply_text(text, reply_markup=buttons, disable_web_page_preview=True, quote=True)

@app.on_message((filters.video | filters.document | filters.audio) & filters.private)
async def handle_media(client, message):
    # Bot will reply directly to the file message (quote=True)
    status_msg = await message.reply_text("🔄 **Extracting file data & generating secure link...**", quote=True)

    try:
        chat_id = message.chat.id
        msg_id = message.id

        media = message.video or message.document or message.audio
        raw_name = getattr(media, "file_name", None) or f"Premium_Media_{msg_id}.mp4"
        file_size_mb = round(media.file_size / (1024 * 1024), 2)

        # Generating core links (Keep them intact for the web player)
        direct_stream_link = f"{STREAM_SERVER_URL}/stream/{chat_id}/{msg_id}"
        web_player_link = f"{WEBSITE_URL}/?url={urllib.parse.quote(direct_stream_link)}&title={urllib.parse.quote(raw_name)}"

        # Professional and premium caption format
        caption = (
            f"✅ **File Successfully Processed!**\n\n"
            f"🎬 **File Name:** `{raw_name}`\n"
            f"📦 **File Size:** `{file_size_mb} MB`\n"
            f"🚀 **Cloud Server:** `Hrry Premium`\n\n"
            f"👇 **Click the button below to Watch or Download seamlessly:**"
        )

        # Removed the direct raw link button as requested
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ Stream & Download Now", url=web_player_link)]
        ])

        await status_msg.edit_text(caption, reply_markup=buttons, disable_web_page_preview=True)

    except Exception as err:
        logging.error(f"Error handling file: {err}")
        await status_msg.edit_text(f"❌ **Failed to process!**\n\n`{str(err)}`")

async def main():
    server = web.Application()
    server.add_routes(routes)
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    
    logging.info(f"Stream Server running on port {PORT}")
    await app.start()
    logging.info("Telegram Bot started successfully!")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.run_forever()
