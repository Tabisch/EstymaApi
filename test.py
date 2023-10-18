import json
import asyncio
import time

from EstymaApiWrapper import EstymaApi

async def testfunction():
    cred = json.load(open("credentials.json"))

    api = EstymaApi(Email= cred["email"], Password= cred["password"])

    await api.initialize()

    f = open("dump_data.txt", "w")
    f.write(json.dumps(await api.getDeviceData(), indent=4))
    f.close()

    f = open("dump_data_textToValues.txt", "w")
    f.write(json.dumps(await api.getDeviceData(textToValues=True), indent=4))
    f.close()

    f = open("dump_settings.txt", "w")
    f.write(json.dumps(await api.getAvailableSettings(), indent=4))
    f.close()
    await api._logout()

asyncio.run(testfunction())