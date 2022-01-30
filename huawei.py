import aiohttp
import logging
import time
import xmltodict
from bs4 import BeautifulSoup

IP = "192.168.8.1"

ERROR_NO_SESSION_ID = 125002
ERROR_TRY_AGAIN     = 111019


def _get_base_url():
    return f"http://{IP}"


class NotSessionIdException(Exception):
    pass


class TryAgainError(Exception):
    pass


class Huawei:
    def __init__(self, proxy=None):
        self.session = None
        self.proxy = proxy

    async def start(self):
        # do simple request to get SessionID for future purpose
        sess_id = "/"
        async with aiohttp.ClientSession(base_url=_get_base_url()) as session:
            while len(sess_id) < 10: #sess_id.find("/") != -1:
                async with session.get("/", proxy=self.proxy) as response:
                    for header in response.raw_headers:
                        if header[0] == b"Set-Cookie":
                            for cookie in header[1].decode().split(';'):
                                a = cookie.split("=")
                                if len(a) == 2 and a[0] == "SessionID":
                                    sess_id = a[1]
                                    break
                            break
                    await response.read()
        # create session for future use
        # note: need to create 'cookie' header by own due to double quoting if there is '\' symbols in sess_id
        self.session = aiohttp.ClientSession(base_url=_get_base_url(),
                                             headers={"Cookie": f"SessionID={sess_id}"})

    async def finish(self):
        if self.session is not None:
            self.session.close()
            self.session = None

    async def _proc_get_request(self, url: str):
        async with self.session.get(url, proxy=self.proxy) as response:
            data = await response.read()
            data_s = data.decode('utf-8')
        return data_s

    async def _proc_post_request(self, url: str, data: bytes, tokens: tuple=None):
        headers = {}
        if tokens is not None:
            headers["__RequestVerificationToken"] = tokens[0]
        async with self.session.post(url,
                                     data=data,
                                     headers=headers,
                                     proxy=self.proxy) as response:
            data = await response.read()
            data_s = data.decode('utf-8')
        return data_s

    def _proc_error(self, data):
        if data.get("error") is not None:
            code = int(data.get("error").get("code", "0"))
            if code == ERROR_NO_SESSION_ID:
                raise NotSessionIdException()
            elif code == ERROR_TRY_AGAIN:
                raise TryAgainError()

    async def _get_tokens(self, url: str):
        data = await self._proc_get_request(url)
        parsed_html = BeautifulSoup(data, features="html.parser")
        tokens = parsed_html.head.find_all('meta', attrs={'name': 'csrf_token'})
        if len(tokens) == 2:
            return (tokens[0]['content'], tokens[1]['content'])
        raise Exception

    async def get_traffic_stat(self):
        data = xmltodict.parse(await self._proc_get_request("/api/monitoring/traffic-statistics"))
        self._proc_error(data)
        return data['response']

    async def check_notifications(self):
        data = xmltodict.parse(await self._proc_get_request("/api/monitoring/check-notifications"))
        self._proc_error(data)
        return data['response']

    async def get_sms_count(self):
        data = xmltodict.parse(await self._proc_get_request("/api/sms/sms-count"))
        self._proc_error(data)
        return data['response']

    async def get_sms_list(self, page: int, count: int):
        sms_tokens = await self._get_tokens("/html/smsinbox.html")

        req = '<?xml version="1.0" encoding="UTF-8"?>'\
              '<request>'\
                    f'<PageIndex>{page}</PageIndex>'\
                    f'<ReadCount>{count}</ReadCount>'\
                    '<BoxType>1</BoxType>'\
                    '<SortType>0</SortType>'\
                    '<Ascending>0</Ascending>'\
                    '<UnreadPreferred>0</UnreadPreferred>'\
              '</request>'
        data = xmltodict.parse(await self._proc_post_request("/api/sms/sms-list", req.encode('utf-8'), sms_tokens))
        self._proc_error(data)
        return data['response']

    async def ussd_request(self, ussd: str, timeout: int=30):
        ussd_tokens = await self._get_tokens("/html/ussd.html")

        req = '<?xml version="1.0" encoding="UTF-8"?>'\
              '<request>'\
                  f'<content>{ussd}</content>'\
                  '<codeType>CodeType</codeType>'\
                  '<timeout></timeout>'\
              '</request>'
        data = xmltodict.parse(await self._proc_post_request("/api/ussd/send", req.encode('utf-8'), ussd_tokens))
        self._proc_error(data)
        done = False
        time_end = time.time() + timeout
        while time_end >= time.time():
            data = xmltodict.parse(await self._proc_get_request("/api/ussd/get"))
            try:
                self._proc_error(data)
                return data['response']
            except TryAgainError:
                await asyncio.sleep(0.5)
            except Exception as e:
                raise e
        return None


if __name__ == "__main__":
    import asyncio

    proxy = 'http://10.8.0.3:8080'
    modem = Huawei(proxy)

    async def main():
        await modem.start()

        while True:
            #print(await modem.get_traffic_stat())
            a = await modem.check_notifications()
#            if int(a["UnreadMessage"]) > 0:
#                print(await modem.get_sms_count())
#                print(await modem.get_sms_list(1, 20))
            print(await modem.ussd_request("*100#"))
            await asyncio.sleep(3)


    loop = asyncio.get_event_loop()
    main_task = loop.create_task(main())
    try:
        loop.run_until_complete(asyncio.wait([main_task]))
    finally:
        loop.close()
