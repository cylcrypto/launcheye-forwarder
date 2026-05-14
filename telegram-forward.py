import asyncio
import os
import re
import logging
import time
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")
CHANNEL_ID = -1003957898973
PUBLIC_CHANNEL_ID = -1003790592798
MAESTRO = "MaestroSniperBot"
SESSION_PATH = "/tmp/launcheye_session"
LAST_ID_FILE = "/tmp/last_id.txt"
LAST_FOMO_ID_FILE = "/tmp/last_fomo_id.txt"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
SOLANA_CA_REGEX = re.compile(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b')

def load_last_id():
    try:
        with open(LAST_ID_FILE) as f:
            return int(f.read().strip())
    except:
        return 0

def save_last_id(lid):
    with open(LAST_ID_FILE, "w") as f:
        f.write(str(lid))

def load_last_fomo_id():
    try:
        with open(LAST_FOMO_ID_FILE) as f:
            return int(f.read().strip())
    except:
        return 0

def save_last_fomo_id(lid):
    with open(LAST_FOMO_ID_FILE, "w") as f:
        f.write(str(lid))

async def send_ca(client, ca, label=""):
    try:
        await client.send_message(MAESTRO, ca)
        logger.info(f"✅ CA ENVOYÉE À MAESTRO{label} → {ca}")
    except FloodWaitError as e:
        logger.warning(f"FloodWait {e.seconds}s")
        await asyncio.sleep(e.seconds + 3)
        await client.send_message(MAESTRO, ca)
        logger.info(f"✅ CA ENVOYÉE À MAESTRO{label} (retry) → {ca}")
    except Exception as e:
        logger.error(f"Erreur envoi : {e}")

async def main():
    last_id = load_last_id()
    last_fomo_id = load_last_fomo_id()
    logger.info(f"Dernier ID chargé : {last_id}")

    while True:
        client = TelegramClient(SESSION_PATH, API_ID, API_HASH,
                                connection_retries=5,
                                retry_delay=3,
                                auto_reconnect=True)
        try:
            await client.start()
            logger.info("✅ Client connecté")

            try:
                fomomulti_entity = await client.get_entity('FomoMulti')
                fomomulti_id = fomomulti_entity.id
                logger.info(f"✅ FomoMulti résolu — ID : {fomomulti_id}")
            except Exception as e:
                fomomulti_id = None
                logger.warning(f"⚠️ FomoMulti non résolu : {e}")

            logger.info(f"🚀 Forwarder actif - Dernier ID : {last_id}")

            async def poll_launcheye():
                nonlocal last_id
                while True:
                    try:
                        async for msg in client.iter_messages(CHANNEL_ID, limit=20, min_id=last_id, reverse=True):
                            if time.time() - msg.date.timestamp() > 300:
                                last_id = max(last_id, msg.id)
                                save_last_id(last_id)
                                continue
                            text = (msg.message or msg.text or "").strip()
                            if text:
                                match = SOLANA_CA_REGEX.search(text)
                                if match:
                                    await send_ca(client, match.group(0))
                            last_id = max(last_id, msg.id)
                            save_last_id(last_id)
                    except Exception as e:
                        logger.warning(f"Poll LaunchEYE error: {e}")
                    await asyncio.sleep(30)

            async def poll_fomomulti():
                nonlocal last_fomo_id
                while True:
                    if fomomulti_id is None:
                        await asyncio.sleep(10)
                        continue
                    try:
                        async for msg in client.iter_messages(fomomulti_id, limit=10, min_id=last_fomo_id, reverse=True):
                            text = (msg.message or msg.text or "").strip()
                            logger.info(f"FomoMulti poll DEBUG: id={msg.id} text={text[:80]}")
                            if text:
                                mcap_match = re.search(r'MC:\s*\$([0-9,.]+)([kKmM]?)', text)
                                if mcap_match:
                                    val = float(mcap_match.group(1).replace(',', ''))
                                    suffix = mcap_match.group(2).lower()
                                    mcap = val * 1_000_000 if suffix == 'm' else val * 1_000 if suffix == 'k' else val
                                    if mcap < 50_000:
                                        match = SOLANA_CA_REGEX.search(text)
                                        if match:
                                            ca = match.group(0)
                                            await client.send_message(MAESTRO, ca)
                                            signal_msg = f"🔥 *FomoMulti Signal*\n`{ca}`\n📊 MCap: ${mcap:,.0f}"
                                            await client.send_message(PUBLIC_CHANNEL_ID, signal_msg, parse_mode='md')
                                            logger.info(f"FomoMulti poll → Maestro: {ca} MCap=${mcap:,.0f}")
                                    else:
                                        logger.info(f"FomoMulti skip: MCap=${mcap:,.0f}")
                            last_fomo_id = max(last_fomo_id, msg.id)
                            save_last_fomo_id(last_fomo_id)
                    except Exception as e:
                        logger.warning(f"Poll FomoMulti error: {e}")
                    await asyncio.sleep(10)

            async def telethon_keepalive():
                while True:
                    try:
                        await client.get_me()
                        logger.info("Telethon keepalive OK")
                    except Exception as e:
                        logger.warning(f"Telethon keepalive error: {e}")
                    await asyncio.sleep(300)

            async def catchup_loop():
                while True:
                    try:
                        await client.catch_up()
                    except Exception as e:
                        logger.warning(f"catch_up error: {e}")
                    await asyncio.sleep(10)

            asyncio.ensure_future(poll_launcheye())
            asyncio.ensure_future(poll_fomomulti())
            asyncio.ensure_future(telethon_keepalive())
            asyncio.ensure_future(catchup_loop())

            await client.run_until_disconnected()

        except Exception as e:
            logger.error(f"Erreur principale : {e}")
        finally:
            try:
                await client.disconnect()
            except:
                pass
            logger.info("Reconnexion dans 5s...")
            await asyncio.sleep(5)

asyncio.run(main())
