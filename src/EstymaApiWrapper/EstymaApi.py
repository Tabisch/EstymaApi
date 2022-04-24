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
    logout_url = "https://{0}/logout"
    update_url = "https://{0}/info_panel_update"
    devicelist_url = "https://{0}/main_panel/get_user_device_list"
    languageSwitch_url = "https://{0}/switchLanguage/{1}}"
    
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    fetchDevicedataBody = "id_urzadzenia={0}"
    loginDataBody = "login={0}&haslo={1}&zaloguj=Login"

    def __init__(self, Email: str, Password: str, scanInterval = 30, language: str = "english"):
        self._Email = urllib.parse.quote(Email)
        self._Password = urllib.parse.quote(Password)
        self._devices = None

        self._initialized = False
        self._loggedIn = False
        self._loginTime = 0
        self._returncode = "None"

        self._deviceData = None

        self._updatingdata = False
        self._lastUpdated = 0
        self._scanInterval = scanInterval

        self._session = None
        self._language = language

    @property
    def initialized(self):
        return self._initialized

    @property
    def returncode(self):
        return self._returncode

    @property
    def devices(self):
        return self._devices

    #login and get devices
    async def initialize(self):
        self._session = aiohttp.ClientSession()
        await self.login()
        await self.switchLanguage(self._language)
        await self.getDevices()
        await self.fetchDevicedata()

    #login to Api
    async def login(self):
        dataformated = self.loginDataBody.format(self._Email, self._Password)

        result = (await self._session.post(self.login_url.format(self.http_url), headers=self.headers, data=dataformated, allow_redirects=False, ssl=False)).status

        if(result == 302):
            self._initialized = True
            self._loggedIn = True
            self._loginTime = int(time.time())
            self._returncode = result
            return

        self._returncode = result

        raise Exception

    async def logout(self):
        if((await self._session.get(self.logout_url.format(self.http_url), allow_redirects=False, ssl=False)).status == 302):
            self._loggedIn = False
            return
        
        raise Exception

    async def relog(self):
        await self.logout()
        await self.login()

    #fetch data for all devices
    async def fetchDevicedatatask(self, deviceid):
        resp = await (await self._session.post(self.update_url.format(self.http_url), headers=self.headers, data=self.fetchDevicedataBody.format(deviceid), ssl=False)).json(content_type='text/html')
        resp["licznik_paliwa_sub1"] = int(str(resp["licznik_paliwa_sub1"])[:-1])
        resp["daystats_data"]["pierwszy_pomiar_paliwa"] = int(str(resp["daystats_data"]["pierwszy_pomiar_paliwa"])[:-1])
        resp["consumption_fuel_current_day"] = resp["licznik_paliwa_sub1"] - resp["daystats_data"]["pierwszy_pomiar_paliwa"]
        resp["device_id"] = deviceid

        return resp

    #init data fetching
    async def fetchDevicedata(self):
        if((int(time.time()) - 3600) > self._loginTime):
            await self.relog()

        self._updatingdata = True

        tasks = []

        for deviceid in list(self._devices.keys()):
            tasks.append(self.fetchDevicedatatask(deviceid))

        responses = await asyncio.gather(*tasks)

        jsonobj = json.loads("{}")

        for response in responses:
            jsonobj[f'{response["device_id"]}'] = response
            
        self._lastUpdated = int(time.time())
        self._updatingdata = False

        #kinda scuffed translation but it works
        self._deviceData = await self.translateApiOutput(json.dumps(jsonobj))

    #get data for device\devices
    async def getDeviceData(self, DeviceID = None):
        if((int(time.time()) - self._scanInterval) > self._lastUpdated):
            if(self._updatingdata == False):
                await self.fetchDevicedata()

        data = json.loads(self._deviceData)

        if(DeviceID == None):
            return data

        return data[f'{DeviceID}']

    async def getDevices(self):

        #could be optimised maybe
        #ripped this stright from the brup suite, works for now so i dont care
        data = 'sEcho=1&iColumns=8&sColumns=&iDisplayStart=0&iDisplayLength=5&mDataProp_0=0&mDataProp_1=1&mDataProp_2=2&mDataProp_3=3&mDataProp_4=4&mDataProp_5=5&mDataProp_6=6&mDataProp_7=7&sSearch=&bRegex=false&sSearch_0=&bRegex_0=false&bSearchable_0=true&sSearch_1=&bRegex_1=false&bSearchable_1=true&sSearch_2=&bRegex_2=false&bSearchable_2=true&sSearch_3=&bRegex_3=false&bSearchable_3=true&sSearch_4=&bRegex_4=false&bSearchable_4=true&sSearch_5=&bRegex_5=false&bSearchable_5=true&sSearch_6=&bRegex_6=false&bSearchable_6=true&sSearch_7=&bRegex_7=false&bSearchable_7=true&iSortingCols=1&iSortCol_0=0&sSortDir_0=asc&bSortable_0=true&bSortable_1=true&bSortable_2=true&bSortable_3=false&bSortable_4=false&bSortable_5=false&bSortable_6=false&bSortable_7=false&sByUserName='

        result = await (await self._session.post(self.devicelist_url.format(self.http_url),data=data , headers=self.headers, ssl=False)).json(content_type='text/html')

        output_json = json.loads('{}')

        if(result["iTotalRecords"] > 0):            
            for device in result["devices_list"]:
                device_template = json.loads(f'{{"name": "{device["0"]}"}}')

                output_json[f'{device["id"]}'] = device_template

        self._devices = output_json

    #function to translate the api response from fetchDevicedata
    async def translateApiOutput(self,input: str):
        translationTable = ""

        with importlib.resources.open_text("EstymaApiWrapper", 'api_translation_table.json') as file:
            translationTable = json.load(file) 

        translated_json = json.dumps(input)

        #somewhat scuffed way to translate all the json keys, but have no clue how to do it another way
        for inputkey in list(translationTable.keys()):
            translated_json =  translated_json.replace(inputkey, translationTable[inputkey])

        return json.loads(translated_json)

    async def switchLanguage(self, targetLanguage: str):
        languageTable = None

        with importlib.resources.open_text("EstymaApiWrapper", 'languageTable.json') as file:
            languageTable = json.load(file)

        url = self.login_url.format(self.http_url, languageTable[targetLanguage.lower()])

        if((await self._session.get(url, allow_redirects=False, ssl=False)).status == 302):
            return

        raise Exception