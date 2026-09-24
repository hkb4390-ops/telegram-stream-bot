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

WEBSITE_URL = os.environ.get("WEBSITE_URL", "https://hrry-stream.vercel.app/")
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

# --- Custom Helper function to extract metadata safely for ANY file type ---
def get_media_meta(message):
    media = message.video or message.audio or message.document or message.photo or message.voice or message.animation
    if not media:
        return None
    
    # Photo objects don't have file_name or mime_type attributes natively
    if message.photo:
        return {
            "file_name": f"Photo_{message.id}.jpg",
            "file_size": media.file_size,
            "mime_type": "image/jpeg",
            "type": "image"
        }
        
    mime = getattr(media, "mime_type", "application/octet-stream")
    name = getattr(media, "file_name", None)
    
    # Generate fallback names if missing (Voice / Animations)
    if not name:
        if message.voice:
            name = f"Voice_{message.id}.ogg"
        elif message.animation:
            name = f"Animation_{message.id}.mp4"
        else:
            name = f"File_{message.id}"
            
    # Classify file for frontend
    if "video" in mime or message.video or message.animation:
        m_type = "video"
    elif "audio" in mime or message.voice or message.audio:
        m_type = "audio"
    elif "image" in mime:
        m_type = "image"
    elif "pdf" in mime:
        m_type = "pdf"
    else:
        m_type = "file"
        
    return {
        "file_name": name,
        "file_size": media.file_size,
        "mime_type": mime,
        "type": m_type
    }
# --------------------------------------------------------------------------

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
        
        meta = get_media_meta(message)
        if not meta:
            return web.Response(status=404, text="Media File Not Found or Unsupported")

        file_size = meta["file_size"]
        mime_type = meta["mime_type"]

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
        f"✨ **Welcome to Hrry.online Cloud Engine Bot!**\n\n"
        f"📁 Mujhe koi bhi **Video, Audio, Photo, PDF** ya **Document File** direct chat me bhejein.\n"
        f"⚡ Main aapko **https://hrry-stream.vercel.app/** par use direct open/stream karne aur high-speed download ka link bana kar dunga."
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Visit Website", url=WEBSITE_URL)]
    ])
    await message.reply_text(text, reply_markup=buttons, disable_web_page_preview=True)

# ADDED EXTRA FILTERS to handle Photo, Voice, and Animations (GIFs)
@app.on_message((filters.video | filters.document | filters.audio | filters.photo | filters.voice | filters.animation) & filters.private)
async def handle_media(client, message):
    status_msg = await message.reply_text("🔄 **Processing media file & generating link...**")

    try:
        chat_id = message.chat.id
        msg_id = message.id
        
        # Using custom helper function to grab info dynamically
        meta = get_media_meta(message)
        if not meta:
            await status_msg.edit_text("❌ **Unsupported media format.**")
            return

        raw_name = meta["file_name"]
        file_size_mb = round(meta["file_size"] / (1024 * 1024), 2)
        media_type = meta["type"]

        direct_stream_link = f"{STREAM_SERVER_URL}/stream/{chat_id}/{msg_id}"
        # Passing media type inside the link so that frontend handles it intelligently
        web_player_link = f"{WEBSITE_URL}/?url={urllib.parse.quote(direct_stream_link)}&title={urllib.parse.quote(raw_name)}&type={media_type}"

        caption = (
            f"🎬 **Title:** `{raw_name}`\n"
            f"📦 **Size:** `{file_size_mb} MB`\n"
            f"🗂 **Type:** `{media_type.upper()}`\n"
            f"🚀 **Host:** `hrry.online`\n\n"
            f"👇 **Niche button par click karke direct Access karein:**"
        )

        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"▶️ Access on hrry.online", url=web_player_link)],
            [InlineKeyboardButton("🔗 Direct Download Link", url=direct_stream_link)]
        ])

        await status_msg.edit_text(caption, reply_markup=buttons, disable_web_page_preview=True)

    except Exception as err:
        logging.error(f"Error handling file: {err}")
        await status_msg.edit_text(f"❌ **Error Details:** `{str(err)}`")

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
