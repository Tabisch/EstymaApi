from asyncio import tasks
from cgitb import text
from http.client import responses
import json
import urllib.parse
import aiohttp
import asyncio
import time
import importlib.resources

class EstymaApi:

    http_url = "igneo.pl"

    login_url = "https://{0}/login"
    update_url = "https://{0}/info_panel_update"
    devicelist_url = "https://{0}/main_panel/get_user_device_list"
    
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    fetchDevicedataBody = "id_urzadzenia={0}"
    logindDataBody = "login={0}&haslo={1}&zaloguj=Login"

    def __init__(self, Username, Password, scanInterval = 30):
        self.Username = urllib.parse.quote(Username)
        self.Password = urllib.parse.quote(Password)
        self.Devices = None

        self._initialized = False
        self._returncode = "None"

        self._deviceData = None

        self._lastUpdated = 0
        self.scanInterval = scanInterval

        self.session = None

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def returncode(self) -> bool:
        return self._returncode

    #login and get devices
    async def initialize(self):
        self.session = aiohttp.ClientSession()
        await self.login()
        await self.getDevices()
        await self.fetchDevicedata()

    #login to Api
    async def login(self):
        dataformated = self.logindDataBody.format(self.Username, self.Password)

        result = (await self.session.post(self.login_url.format(self.http_url), headers=self.headers, data=dataformated, allow_redirects=False, ssl=False)).status

        if(result == 302):
            self._initialized = True
            self._returncode = result
            return

        raise Exception

    #fetch data for all devices
    async def fetchDevicedatatask(self, deviceid):
        resp = await (await self.session.post(self.update_url.format(self.http_url), headers=self.headers, data=self.fetchDevicedataBody.format(deviceid), ssl=False)).json(content_type='text/html')

        resp["device_id"] = deviceid

        return resp

    #init data fetching
    async def fetchDevicedata(self):
        tasks = []

        for deviceid in list(self.Devices.keys()):
            tasks.append(self.fetchDevicedatatask(deviceid))

        responses = await asyncio.gather(*tasks)

        jsonobj = json.loads("{}")

        for response in responses:
            jsonobj[f'{response["device_id"]}'] = response
            
        self._lastUpdated = int(time.time())

        #kinda scuffed translation but it works
        self._deviceData = await self.translateApiOutput(json.dumps(jsonobj))

    #get data for device\devices
    async def getDeviceData(self, DeviceID = None):
        if(int(time.time()) - 30 > self._lastUpdated):
            self.fetchDevicedata()

        data = json.loads(self._deviceData)

        if(DeviceID == None):
            return data

        return data[f'{DeviceID}']

    async def getDevices(self):

        #could be optimised maybe
        #ripped this stright from the brup suite, works for now so i dont care
        data = 'sEcho=1&iColumns=8&sColumns=&iDisplayStart=0&iDisplayLength=5&mDataProp_0=0&mDataProp_1=1&mDataProp_2=2&mDataProp_3=3&mDataProp_4=4&mDataProp_5=5&mDataProp_6=6&mDataProp_7=7&sSearch=&bRegex=false&sSearch_0=&bRegex_0=false&bSearchable_0=true&sSearch_1=&bRegex_1=false&bSearchable_1=true&sSearch_2=&bRegex_2=false&bSearchable_2=true&sSearch_3=&bRegex_3=false&bSearchable_3=true&sSearch_4=&bRegex_4=false&bSearchable_4=true&sSearch_5=&bRegex_5=false&bSearchable_5=true&sSearch_6=&bRegex_6=false&bSearchable_6=true&sSearch_7=&bRegex_7=false&bSearchable_7=true&iSortingCols=1&iSortCol_0=0&sSortDir_0=asc&bSortable_0=true&bSortable_1=true&bSortable_2=true&bSortable_3=false&bSortable_4=false&bSortable_5=false&bSortable_6=false&bSortable_7=false&sByUserName='

        result = await (await self.session.post(self.devicelist_url.format(self.http_url),data=data , headers=self.headers, ssl=False)).json(content_type='text/html')

        output_json = json.loads('{}')

        if(result["iTotalRecords"] > 0):            
            for device in result["devices_list"]:
                device_template = json.loads(f'{{"name": "{device["0"]}"}}')

                output_json[f'{device["device_id"]}'] = device_template

        self.Devices = output_json

    #function to translate the api response from fetchDevicedata
    async def translateApiOutput(self,input):
        translationTable = ""

        with importlib.resources.open_text("EstymaApiWrapper", 'api_translation_table.json') as file:
            translationTable = json.load(file) 

        translated_json = json.dumps(input)

        #somewhat scuffed way to translate all the json keys, but have no clue how to do it another way
        for inputkey in list(translationTable.keys()):
            translated_json =  translated_json.replace(inputkey, translationTable[inputkey])

        return json.loads(translated_json)
