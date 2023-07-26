import json
import asyncio
import time

from EstymaApiWrapper import EstymaApi

async def testfunction():
    cred = json.load(open("credentials.json"))

    api = EstymaApi(Email= cred["email"], Password= cred["password"])

    await api.initialize()

    print(json.dumps(await api.getDeviceData("4251681784"), indent=4))

    await api._logout()

asyncio.run(testfunction())