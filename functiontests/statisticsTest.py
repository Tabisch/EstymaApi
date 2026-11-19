import json
import asyncio
import datetime

from EstymaApiWrapper import EstymaApi

async def testfunction():
    cred = json.load(open("credentials.json"))

    api = EstymaApi(Email= cred["email"], Password= cred["password"])

    await api.initialize()

    deviceID = list((await api.getDevices()).keys())[0]

    #statistics for today
    statistics = await api.getStatistics(deviceID)

    for seriesID, series in statistics.items():
        print(f'{seriesID} ({series["name"]}): {len(series["data"])} points, last: {series["data"][-1] if series["data"] else None}')

    #statistics for a specific day
    statistics = await api.getStatistics(deviceID, dateTo=datetime.date.today() - datetime.timedelta(days=1))

    f = open("dump_statistics.txt", "w")
    f.write(json.dumps(statistics, indent=4))
    f.close()

    await api._logout()

asyncio.run(testfunction())
