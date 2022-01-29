import logging
import datetime
import time
import json
import os
import sys
import pyrogram
import asyncio
from signal import SIGINT, SIGTERM


def load_settings(fname: str) -> dict:
    with open(fname, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    # init logging
    if not os.path.exists("log"):
        os.mkdir("log")
    logging.basicConfig(filename=f"log/{datetime.datetime.now().strftime('%Y.%m.%d_%H.%M.%S')}.log",
                        format="%(asctime)s %(levelname)-8s %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S",
                        level=logging.INFO)
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
    logging.info(f"started with pid {os.getpid()}")

    # load config
    sett = load_settings("config.json")

    # create tg client
    tg_client = pyrogram.Client(sett["telegram"]["session"], sett["telegram"]["api_id"], sett["telegram"]["api_hash"])


    @tg_client.on_message()
    async def on_msg(client: pyrogram.Client, message: pyrogram.types.Message):
        pass


    async def shutdown(signal, loop):
        logging.info(f"Received exit signal {signal.name}...")
        tasks = [t for t in asyncio.all_tasks() if t is not
                 asyncio.current_task()]

        for task in tasks:
            task.cancel()

        logging.info("Cancelling outstanding tasks")
        await asyncio.gather(*tasks, return_exceptions=True)
        loop.stop()


    async def pyrogram_main(sem_tg_ready: asyncio.Semaphore):
        try:
            await tg_client.start()
            logging.info("telegram started")
            sem_tg_ready.release()

            await pyrogram.idle()
        except Exception as E:
            logging.exception("tg exception")


    async def main(loop, sem: asyncio.Semaphore):
        # wait until everyone is ready
        await sem.acquire()

        # get chat id for sending messages
        logging.info("getting chat_id...")
        chat_id = None
        while chat_id is None:
            await asyncio.sleep(1)

            try:
                if tg_client.is_connected:
                    a = await tg_client.send(pyrogram.raw.functions.messages.GetAllChats(except_ids=[]))
                    if isinstance(a, pyrogram.raw.types.messages.Chats):
                        for chat in a.chats:
                            if chat.title == sett["telegram-chat-name"]:
                                if isinstance(chat, pyrogram.raw.types.Channel):
                                    chat_id = int(f"-100{abs(chat.id)}")
                                    break
                                elif isinstance(chat, pyrogram.raw.types.Chat) and not chat.deactivated:
                                    chat_id = -1 * abs(chat.id)
                                    break
            except pyrogram.errors.exceptions.flood_420.FloodWait as e:
                logging.warning(f"woops, flooding. Waiting for {e.x} seconds")
                await asyncio.sleep(e.x)
            except Exception as e:
                logging.exception("get chat_id exception")

        logging.info("chat_id is OK")

        # send hello message to the chat
        await tg_client.send_message(chat_id, "started", disable_notification=True)

        # main loop
#        keep_alive_time = time.time() + sett["keep-alive-interval"]
        while True:
#            except Exception as e:
#                logging.exception("main loop exception")

#            logging.info("sleep...")
            await asyncio.sleep(1) #sett["request-pause"])


    # start main loop
    loop = asyncio.get_event_loop()
    for signal in [SIGINT, SIGTERM]:
        loop.add_signal_handler(signal, lambda s=signal: asyncio.create_task(shutdown(s, loop)))
    sem_tg_ready = asyncio.Semaphore(0)
    pyrogram_task = asyncio.ensure_future(pyrogram_main(sem_tg_ready))
    main_task = asyncio.ensure_future(main(loop, sem_tg_ready))
    try:
        loop.run_until_complete(asyncio.wait([pyrogram_task, main_task]))
    finally:
        loop.close()
