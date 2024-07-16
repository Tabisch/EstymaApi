import json
import asyncio

from EstymaApiWrapper import EstymaApi

async def testfunction():
    cred = json.load(open("credentials.json"))

    api = EstymaApi(Email= cred["email"], Password= cred["password"])

    print(await api.testCredentials())

asyncio.run(testfunction())