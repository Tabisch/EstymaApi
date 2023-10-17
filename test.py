import json
import asyncio
import time

from EstymaApiWrapper import EstymaApi

async def testfunction():
    cred = json.load(open("credentials.json"))

    api = EstymaApi(Email= cred["email"], Password= cred["password"])

    await api.initialize()

    try:
        await api.changeSetting(4251681784, "temp_boiler_target_sub1", 61)
    except:
        await api.changeSetting(4251681784, "temp_boiler_target_sub1", 60)

    while await api.isUpdating(4251681784, "temp_boiler_target_sub1"):
        print(await api.getSettingChangeState())
        time.sleep(10)

    await api._logout()

asyncio.run(testfunction())