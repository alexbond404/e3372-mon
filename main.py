import logging
import datetime
import time
import json
import os
import sys
import pyrogram
import asyncio
from signal import SIGINT, SIGTERM

import huawei


def load_settings(fname: str) -> dict:
    with open(fname, encoding="utf-8") as f:
        return json.load(f)

def bytes_to_str(val):
    if val < 1024:
        units = "B"
    elif val < 1024**2:
        val = val / 1024
        units = "KB"
    elif val < 1024**3:
        val = val / 1024**2
        units = "MB"
    else:
        val = val / 1024**3
        units = "GB"
    return f"{val:.2f} {units}"


if __name__ == "__main__":
    start_time = time.time()

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

    # create modem client
    modem = huawei.Huawei(sett.get("proxy"))


    @tg_client.on_message()
    async def on_msg(client: pyrogram.Client, message: pyrogram.types.Message):
        if message.chat.title == sett["telegram-chat-name"]:
            m = message.text.strip()
            msg = m

            if len(msg):
                reply_msg = ''
                if msg.startswith("@hello"):
                    reply_msg = "hello!"
                elif msg.startswith("@uptime"):
                    reply_msg = "uptime {}".format(int(time.time() - start_time))
                elif m.startswith("@ussd"):
                    m = m.split()
                    if len(m) < 2:
                        reply_msg = "wrong params"
                    else:
                        try:
                            reply_msg = (await modem.ussd_request(m[1]))['content']
                        except Exception as e:
                            reply_msg = "exception"
                elif m.startswith("@stat"):
                    try:
                        stat = await modem.get_month_traffic_stat()
                        reply_msg = "\r\n".join([f"Время подключения: {stat['MonthDuration']}",
                                                 f"Upload: {bytes_to_str(int(stat['CurrentMonthUpload']))}",
                                                 f"Download: {bytes_to_str(int(stat['CurrentMonthDownload']))}"])
                    except Exception as e:
                        reply_msg = "exception"
                else:
                    reply_msg = "error: unknown command"

                await client.read_history(message.chat.id, message.message_id)
                await message.reply_text(reply_msg, quote=True)


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

        await modem.start()

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
        sms_check_time = time.time()
        while True:
            try:
                # check new sms periodically
                if time.time() >= sms_check_time:
                    sms_check_time = time.time() + sett["sms-check-period"]
                    while int((await modem.get_sms_count())['LocalInbox']) > 0:
                        sms_list = await modem.get_sms_list()
                        # workaround for 1 message due to wrong parsing
                        if not isinstance(sms_list["Messages"]["Message"], list):
                            x = sms_list["Messages"]["Message"]
                            sms_list["Messages"]["Message"] = [x]
                        # iterate over all SMS
                        for sms in sms_list["Messages"]["Message"]:
                            await tg_client.send_message(chat_id, f"sms\r\n{sms['Date']}\r\n{sms['Phone']}\r\n{sms['Content']}")
                            await modem.sms_delete(int(sms['Index']))
            except Exception as e:
                logging.exception("main loop exception")

            # delay not to consume CPU time
            await asyncio.sleep(1)


    # start main loop
    loop = asyncio.get_event_loop()
    for signal in [SIGINT, SIGTERM]:
        loop.add_signal_handler(signal, lambda s=signal: asyncio.create_task(shutdown(s, loop)))
    sem_tg_ready = asyncio.Semaphore(0)
    pyrogram_task = loop.create_task(pyrogram_main(sem_tg_ready))
    main_task = loop.create_task(main(loop, sem_tg_ready))
    try:
        loop.run_until_complete(asyncio.wait([pyrogram_task, main_task]))
    finally:
        loop.close()
