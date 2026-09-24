import asyncio

# Python 3.10+ Event Loop Fix
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import os
import sys
import logging
import urllib.parse
import gc
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, RPCError
from aiohttp import web

# ==================== CONFIGURATION ====================
API_ID = int(os.environ.get("API_ID", "34305725"))
API_HASH = os.environ.get("API_HASH", "a7439c105c050b5011a90bda4f0e1e90")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8899747292:AAGusFkBrquTmi2gA2DDEm_4f9Woh3Q5XQQ")

# Private Log Channel ID
LOG_CHANNEL = os.environ.get("LOG_CHANNEL", "-1004364861797") 

WEBSITE_URL = os.environ.get("WEBSITE_URL", "https://hrry-stream.vercel.app/").rstrip("/")
PORT = int(os.environ.get("PORT", "8080"))

raw_stream_url = os.environ.get("STREAM_SERVER_URL", "http://localhost:8080").rstrip("/")
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

# Global CORS Headers
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Range, Content-Type, Accept, Authorization, X-Requested-With",
}

def get_media_meta(message):
    media = message.video or message.audio or message.document or message.photo or message.voice or message.animation
    if not media:
        return None
    
    if message.photo:
        return {
            "file_name": f"Photo_{message.id}.jpg",
            "file_size": media.file_size,
            "mime_type": "image/jpeg",
            "type": "image"
        }
        
    mime = getattr(media, "mime_type", "application/octet-stream")
    name = getattr(media, "file_name", None)
    
    if not name:
        if message.voice:
            name = f"Voice_{message.id}.ogg"
        elif message.animation:
            name = f"Animation_{message.id}.mp4"
        else:
            name = f"File_{message.id}"
            
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

# Handle All CORS Preflight Requests
@routes.options("/{path:.*}")
async def global_options_handler(request):
    return web.Response(status=200, headers=CORS_HEADERS)

@routes.get("/")
async def root_handler(request):
    return web.json_response({
        "status": "online",
        "service": "Hrry Direct Web Engine",
        "target_website": WEBSITE_URL
    }, headers=CORS_HEADERS)

# --- 1. DIRECT WEB UPLOAD ENDPOINT ---
@routes.post("/upload")
async def upload_from_web(request):
    temp_path = None
    try:
        reader = await request.multipart()
        field = await reader.next()
        
        if not field or not field.filename:
            return web.json_response(
                {"status": "error", "message": "No file provided"}, 
                status=400, 
                headers=CORS_HEADERS
            )
            
        filename = field.filename
        os.makedirs("temp_uploads", exist_ok=True)
        temp_path = os.path.join("temp_uploads", filename)

        # Stream chunk to local disk
        with open(temp_path, "wb") as f:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                f.write(chunk)

        # Chat ID Conversion
        target_chat = LOG_CHANNEL
        try:
            target_chat = int(target_chat)
        except ValueError:
            pass

        # Send File to Telegram Private Channel
        initial_caption = f"🌐 **Web Upload:** `{filename}`\n👤 **Source:** Website Upload"
        try:
            sent_msg = await app.send_document(
                chat_id=target_chat,
                document=temp_path,
                caption=initial_caption
            )
        except FloodWait as f_err:
            logging.warning(f"Telegram Rate Limited: Waiting {f_err.value} seconds")
            await asyncio.sleep(f_err.value)
            sent_msg = await app.send_document(
                chat_id=target_chat,
                document=temp_path,
                caption=initial_caption
            )
        except RPCError as rpc_err:
            logging.error(f"Telegram RPC Error: {rpc_err}")
            return web.json_response(
                {"status": "error", "message": f"Telegram Error: {str(rpc_err)}"}, 
                status=500, 
                headers=CORS_HEADERS
            )

        meta = get_media_meta(sent_msg)
        chat_id = sent_msg.chat.id
        msg_id = sent_msg.id

        direct_stream_link = f"{STREAM_SERVER_URL}/stream/{chat_id}/{msg_id}"
        web_player_link = f"{WEBSITE_URL}/?url={urllib.parse.quote(direct_stream_link)}&title={urllib.parse.quote(filename)}&type={meta['type']}"

        # Update log channel caption with link
        try:
            log_caption = (
                f"📁 **File:** `{filename}`\n"
                f"📦 **Size:** `{round(meta['file_size'] / (1024 * 1024), 2)} MB`\n"
                f"👤 **Source:** Website UI\n\n"
                f"🔗 **Web Player Link:** {web_player_link}"
            )
            await sent_msg.edit_caption(log_caption)
        except Exception as edit_err:
            logging.warning(f"Channel caption edit error: {edit_err}")

        return web.json_response({
            "status": "success",
            "file_name": filename,
            "file_size": meta["file_size"],
            "type": meta["type"],
            "stream_link": direct_stream_link,
            "player_link": web_player_link
        }, headers=CORS_HEADERS)

    except Exception as e:
        logging.error(f"Web Upload Internal Error: {e}")
        return web.json_response(
            {"status": "error", "message": f"Server Internal Error: {str(e)}"}, 
            status=500, 
            headers=CORS_HEADERS
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as clean_err:
                logging.warning(f"Temp File Removal Failed: {clean_err}")
        gc.collect()

# --- STREAMING ENGINE ENDPOINT ---
@routes.get("/stream/{chat_id}/{message_id}")
async def stream_handler(request):
    try:
        chat_id = int(request.match_info["chat_id"])
        msg_id = int(request.match_info["message_id"])
        
        message = await app.get_messages(chat_id, msg_id)
        meta = get_media_meta(message)
        if not meta:
            return web.Response(status=404, text="Media File Not Found", headers=CORS_HEADERS)

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
            return web.Response(status=416, text="Range Not Satisfiable", headers=CORS_HEADERS)

        length = (to_bytes - from_bytes) + 1
        headers = {
            "Content-Type": mime_type,
            "Content-Range": f"bytes {from_bytes}-{to_bytes}/{file_size}",
            "Content-Length": str(length),
            "Accept-Ranges": "bytes",
            **CORS_HEADERS
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
        return web.Response(status=500, text=f"Streaming Error: {str(e)}", headers=CORS_HEADERS)

# --- TELEGRAM BOT COMMANDS ---
@app.on_message(filters.command("start") & filters.private)
async def start_msg(client, message):
    text = (
        f"✨ **Welcome to Hrry Cloud Engine!**\n\n"
        f"📁 Media file send karein direct streaming link ke liye."
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Visit Website", url=WEBSITE_URL)]
    ])
    await message.reply_text(text, reply_markup=buttons, disable_web_page_preview=True)

# --- 2. TELEGRAM PM UPLOAD -> PRIVATE CHANNEL LOG WITH USER DETAILS ---
@app.on_message((filters.video | filters.document | filters.audio | filters.photo | filters.voice | filters.animation) & filters.private)
async def handle_media(client, message):
    status_msg = await message.reply_text("🔄 **Processing and backing up media...**")

    try:
        target_chat = LOG_CHANNEL
        try:
            target_chat = int(target_chat)
        except ValueError:
            pass

        # User Profile Details
        user = message.from_user
        user_id = user.id if user else "Unknown"
        user_name = user.first_name if user else "Unknown User"
        if user and user.last_name:
            user_name += f" {user.last_name}"
        username_str = f"@{user.username}" if (user and user.username) else "No Username"

        meta = get_media_meta(message)
        if not meta:
            await status_msg.edit_text("❌ **Unsupported media format.**")
            return

        raw_name = meta["file_name"]
        file_size_mb = round(meta["file_size"] / (1024 * 1024), 2)
        media_type = meta["type"]

        # Step A: Copy file to Private Channel with User Details Initial Caption
        initial_log_caption = (
            f"📁 **File Name:** `{raw_name}`\n"
            f"📦 **Size:** `{file_size_mb} MB`\n"
            f"👤 **Uploaded By:** {user_name}\n"
            f"🆔 **User ID:** `{user_id}`\n"
            f"🌐 **Username:** {username_str}"
        )

        try:
            log_msg = await message.copy(chat_id=target_chat, caption=initial_log_caption)
            chat_id = log_msg.chat.id
            msg_id = log_msg.id
        except Exception as copy_err:
            logging.error(f"Failed to copy to channel: {copy_err}")
            chat_id = message.chat.id
            msg_id = message.id

        # Step B: Links Generation
        direct_stream_link = f"{STREAM_SERVER_URL}/stream/{chat_id}/{msg_id}"
        web_player_link = f"{WEBSITE_URL}/?url={urllib.parse.quote(direct_stream_link)}&title={urllib.parse.quote(raw_name)}&type={media_type}"

        # Update Channel Log with Web Link
        final_log_caption = (
            f"📁 **File Name:** `{raw_name}`\n"
            f"📦 **Size:** `{file_size_mb} MB`\n"
            f"👤 **Uploaded By:** [{user_name}](tg://user?id={user_id})\n"
            f"🆔 **User ID:** `{user_id}`\n"
            f"🌐 **Username:** {username_str}\n\n"
            f"🔗 **Web Player Link:** {web_player_link}"
        )
        try:
            if 'log_msg' in locals():
                await log_msg.edit_caption(final_log_caption)
        except Exception as edit_err:
            logging.warning(f"Failed to update channel log: {edit_err}")

        # Step C: Reply to User in Bot PM (ONLY Website Link Button, NO Direct Stream Button)
        user_caption = (
            f"🎬 **Title:** `{raw_name}`\n"
            f"📦 **Size:** `{file_size_mb} MB`\n"
            f"🚀 **Host:** `hrry.online`\n\n"
            f"👇 **Niche button par click karke dekhein / download karein:**"
        )

        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ Watch / Download on Website", url=web_player_link)]
        ])

        await status_msg.edit_text(user_caption, reply_markup=buttons, disable_web_page_preview=True)

    except Exception as err:
        logging.error(f"Error handling file: {err}")
        await status_msg.edit_text(f"❌ **Error Details:** `{str(err)}`")
    finally:
        gc.collect()

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

