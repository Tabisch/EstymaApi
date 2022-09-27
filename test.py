import json
import asyncio
import time

from EstymaApiWrapper import EstymaApi

async def testfunction():
    cred = json.load(open("credentials.json"))

    api = EstymaApi(Email= cred["email"], Password= cred["password"])

    await api.initialize()

    await api.changeSetting(deviceID=(list((await api.getDevices()).keys())[0]),settingName="temp_boiler_target_sub1",targetValue=61)

    while(True):
        print(await api.getSettingChangeState())
        time.sleep(10)

asyncio.run(testfunction())