import json
import asyncio
import time

from EstymaApiWrapper import EstymaApi

async def testfunction():
    cred = json.load(open("credentials.json"))

    api = EstymaApi(Email= cred["email"], Password= cred["password"], Domain="net.estyma.pl")

    print(await api.testCredentials())

asyncio.run(testfunction())