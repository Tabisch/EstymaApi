import json
import asyncio
import time

from EstymaApiWrapper import EstymaApi

async def testfunction():
    deviceID = 4251681784
    cred = json.load(open("credentials.json"))

    api = EstymaApi(Email= cred["username"], Password= cred["password"])
    await api.initialize()

    deviceData = json.dumps(await api.getDeviceData(deviceID), indent= 4)

    print(deviceData)

    await api.changeSetting(deviceID=deviceID, settingName="temp_boiler_target_sub1",targetValue=60)

    while(True):
        print(await api.getSettingChangeState())
        time.sleep(5)

asyncio.run(testfunction())