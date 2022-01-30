import aiohttp
import logging
import xmltodict

IP = "192.168.8.1"


def _get_base_url():
    return f"http://{IP}"


class NotSessionIdException(Exception):
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

    async def _proc_get_request(self, url):
        async with self.session.get(url, proxy=self.proxy) as response:
            data = await response.read()
            data_s = data.decode('utf-8')
        return data_s

    async def get_traffic_stat(self):
        data = await self._proc_get_request("/api/monitoring/traffic-statistics")
        j = xmltodict.parse(data)
        if j.get("error") is not None:
            raise NotSessionIdException()
        return j['response']


if __name__ == "__main__":
    import asyncio

    proxy = 'http://10.8.0.3:8080'
    modem = Huawei(proxy)

    async def main():
        await modem.start()

        while True:
            print(await modem.get_traffic_stat())
            await asyncio.sleep(3)


    loop = asyncio.get_event_loop()
    main_task = loop.create_task(main())
    try:
        loop.run_until_complete(asyncio.wait([main_task]))
    finally:
        loop.close()
