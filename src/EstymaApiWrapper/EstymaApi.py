import json
import urllib.parse
import aiohttp
import asyncio
import time
import importlib.resources
from bs4 import BeautifulSoup
import re
from .CustomErrors import SettingNotAvailableException, SettingAlreadyHasTargetValue, ClientNotInitialized

class EstymaApi:
    http_url = "igneo.pl"

    login_url = "https://{0}/login"
    logout_url = "https://{0}/logout"
    deviceSettings_url = "https://{0}/device/{1}"
    update_url = "https://{0}/info_panel_update"
    changeSetting_url = "https://{0}/info_set_order"
    settingChangeState_url = "https://{0}/info_check_order"
    devicelist_url = "https://{0}/main_panel/get_user_device_list"

    languageSwitch_url = "https://{0}/switchLanguage/{1}}"
    
    headers = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
    fetchDevicedataBody = "id_urzadzenia={0}"
    loginDataBody = "login={0}&haslo={1}&zaloguj=Login"
    changeSettingBody = "id_urzadzenia={0}&name={1}&value={2}"
    settingChangeStateBody = "id_urzadzenia={0}&order_number={1}"

    updateDiffRegex = r"(\d+)d (\d+)h:(\d+)m:(\d+)s"

    def __init__(self, Email: str, Password: str, scanInterval = 30, language: str = "english", staleDataThresholdSeconds: int = 300):
        self._Email = urllib.parse.quote(Email)
        self._Password = urllib.parse.quote(Password)
        self._devices = None
        self._availableSettings = json.loads("{}")

        self._initialized = False
        self._loggedIn = False
        self._loginTime = 0
        self._loginTimeLimit = 3600

        self._staleDataThresholdSeconds = staleDataThresholdSeconds

        self._deviceData = "{}"

        self._updatingdata = False
        self._lastUpdated = 0
        self._scanInterval = scanInterval

        self._session = None
        self._language = language

        with importlib.resources.open_text("EstymaApiWrapper", 'api_translation_table.json') as file:
            self._translationTable = json.load(file) 

        self._settingChangeState_list = json.loads("{}")
        self._settingChangeState_lastUpdate = 0
        self._settingChangeState_rateLimitSeconds = 10

    @property
    def initialized(self):
        return self._initialized

    @property
    def loggedIn(self):
        return self._loggedIn

    @property
    def devices(self):
        return self._devices

    @property
    def updatingData(self):
        return self._updatingdata

    async def _makeRequest(self, type: str, url, data: str = None):
        if(type == "post"):
            return await self._session.post(url, headers=self.headers, data=data, allow_redirects=False, ssl=False)

        if(type == "get"):
            return await self._session.get(url, allow_redirects=False, ssl=False)

        raise Exception

    #login and get devices
    async def initialize(self, throw_Execetion = True):
        try:
            await self._login()
            await self.switchLanguage(self._language)
            await self._fetchDevices()
            await self._fetchDevicedata()
            await self._fetchAvailableDeviceSettings()
        except Exception as e:
            print(e)
            if(throw_Execetion):
                raise Exception

        return self.initialized

    #login to Api
    async def _login(self):
        self._session = aiohttp.ClientSession()

        dataformated = self.loginDataBody.format(self._Email, self._Password)

        result = (await self._makeRequest("post", self.login_url.format(self.http_url), data=dataformated)).status

        if(result == 302):
            self._initialized = True
            self._loggedIn = True
            self._loginTime = int(time.time())
            return

        raise Exception

    async def _logout(self):
        self._loggedIn = False

        try:
            if((await self._makeRequest("get", self.logout_url.format(self.http_url))).status == 302):
                return
        except:
            return
        
        return

    async def _relog(self):
        try:
            await self._logout()
            await self._login()
            await self.switchLanguage(self._language)
        except:
            return

    #fetch data for all devices
    async def _fetchDevicedatatask(self, deviceid):
        resp = await (await self._makeRequest("post", self.update_url.format(self.http_url), data=self.fetchDevicedataBody.format(deviceid))).json(content_type='text/html')
        resp["licznik_paliwa_sub1"] = int(str(resp["licznik_paliwa_sub1"])[:-1])
        resp["daystats_data"]["pierwszy_pomiar_paliwa"] = int(str(resp["daystats_data"]["pierwszy_pomiar_paliwa"])[:-1])
        resp["consumption_fuel_current_day"] = resp["licznik_paliwa_sub1"] - resp["daystats_data"]["pierwszy_pomiar_paliwa"]
        resp["online"]["diffSeconds"] = await self._calculateUpdateDiffSeconds(resp["online"]["diff"])
        resp["dataUpToDate"] = await self._determineDataUpToDate(resp["online"]["diffSeconds"])
        resp["device_id"] = deviceid

        return resp
    
    async def _determineDataUpToDate(self, diffSeconds: int):
        if diffSeconds < self._staleDataThresholdSeconds:
            return True
        else:
            return False

    async def _calculateUpdateDiffSeconds(self, diffString: str):
        seconds = 0

        dataSegments = re.search(self.updateDiffRegex, diffString)

        seconds += int(dataSegments.group(1)) * 24 * 60 * 60
        seconds += int(dataSegments.group(2)) * 60 * 60
        seconds += int(dataSegments.group(3)) * 60
        seconds += int(dataSegments.group(4))

        return seconds

    #init data fetching
    async def _fetchDevicedata(self, translateData= True):
        self._updatingdata = True

        if((int(time.time()) - self._loginTimeLimit) > self._loginTime):
            await self._relog()

        tasks = []

        for deviceid in list(self._devices.keys()):
            tasks.append(self._fetchDevicedatatask(deviceid))

        responses = await asyncio.gather(*tasks)

        jsonobj = json.loads("{}")

        for response in responses:
            jsonobj[f'{response["device_id"]}'] = response
            
        self._lastUpdated = int(time.time())
        self._updatingdata = False

        if(translateData):
            #kinda scuffed translation but it works
            self._deviceData = await self._translateApiOutput(json.dumps(jsonobj))
        else:
            self._deviceData = jsonobj

    async def getDevices(self):
        if(self.initialized == False):
            raise ClientNotInitialized

        return self._devices

    #get data for device\devices
    async def getDeviceData(self, DeviceID = None):
        if(self.initialized == False):
            raise ClientNotInitialized

        if((int(time.time()) - self._scanInterval) > self._lastUpdated):
            if(self._updatingdata == False):
                try:
                    await self._fetchDevicedata()
                except:
                    await self._relog()
                    self._updatingdata = False
                    print("getDeviceData except. Delivering previous data.")

        data = json.loads(self._deviceData)

        if(DeviceID == None):
            return data

        return data[f'{DeviceID}']

    async def _fetchDevices(self):
        #could be optimised maybe
        #ripped this stright from the brup suite, works for now so i dont care
        data = 'sEcho=1&iColumns=8&sColumns=&iDisplayStart=0&iDisplayLength=5&mDataProp_0=0&mDataProp_1=1&mDataProp_2=2&mDataProp_3=3&mDataProp_4=4&mDataProp_5=5&mDataProp_6=6&mDataProp_7=7&sSearch=&bRegex=false&sSearch_0=&bRegex_0=false&bSearchable_0=true&sSearch_1=&bRegex_1=false&bSearchable_1=true&sSearch_2=&bRegex_2=false&bSearchable_2=true&sSearch_3=&bRegex_3=false&bSearchable_3=true&sSearch_4=&bRegex_4=false&bSearchable_4=true&sSearch_5=&bRegex_5=false&bSearchable_5=true&sSearch_6=&bRegex_6=false&bSearchable_6=true&sSearch_7=&bRegex_7=false&bSearchable_7=true&iSortingCols=1&iSortCol_0=0&sSortDir_0=asc&bSortable_0=true&bSortable_1=true&bSortable_2=true&bSortable_3=false&bSortable_4=false&bSortable_5=false&bSortable_6=false&bSortable_7=false&sByUserName='

        result = await (await self._makeRequest("post", self.devicelist_url.format(self.http_url),data=data)).json(content_type='text/html')

        output_json = json.loads('{}')

        if(result["iTotalRecords"] > 0):            
            for device in result["devices_list"]:
                device_template = json.loads(f'{{"name": "{device["0"]}"}}')

                output_json[f'{device["id"]}'] = device_template

        self._devices = output_json

    #function to translate the api response from _fetchDevicedata
    async def _translateApiOutput(self,input: str):
        translated_json = json.dumps(input)

        #somewhat scuffed way to translate all the json keys, but have no clue how to do it another way
        for inputkey in list(self._translationTable["deviceState"].keys()):
            translated_json =  translated_json.replace(inputkey, self._translationTable["deviceState"][inputkey])

        return json.loads(translated_json)

    async def switchLanguage(self, targetLanguage: str):
        if(self.initialized == False):
            raise ClientNotInitialized

        languageTable = None

        with importlib.resources.open_text("EstymaApiWrapper", 'languageTable.json') as file:
            languageTable = json.load(file)

        url = self.login_url.format(self.http_url, languageTable[targetLanguage.lower()])

        await self._makeRequest("get", url)

    #send request to change a Setting
    async def changeSetting(self, deviceID: int, settingName: str, targetValue: int):
        if(self.initialized == False):
            raise ClientNotInitialized

        if((await self.getDeviceData(deviceID))[settingName] == targetValue):
            raise SettingAlreadyHasTargetValue

        if(str(targetValue) not in self._availableSettings[f"{deviceID}"][settingName].keys()):
            raise SettingNotAvailableException
        
        settingNameTranslated = ""
        for key, value in self._translationTable["deviceState"].items():
             if value == settingName:
                settingNameTranslated = key

        dataBody = self.changeSettingBody.format(deviceID, settingNameTranslated, targetValue)

        url = self.changeSetting_url.format(self.http_url)

        changeID = await (await self._makeRequest("post", url, data=dataBody)).text()

        #create key for device if does not exist
        if(deviceID not in self._settingChangeState_list):
            self._settingChangeState_list[deviceID] = {}

        #create key for stateChange if does not exist
        self._settingChangeState_list[deviceID][changeID] = {}

        self._settingChangeState_list[deviceID][changeID]["settingName"] = settingName
        self._settingChangeState_list[deviceID][changeID]["targetValue"] = targetValue
        self._settingChangeState_list[deviceID][changeID]["state"] = ""

    async def _handleSettingChangeRequest(self,deviceID: int, changeID: int):
        requestBody=self.settingChangeStateBody.format(deviceID, changeID)

        returnobj = {}
        returnobj["deviceID"] = deviceID
        returnobj["changeID"] = changeID

        state = ""

        #idk why but the request seam to fail like every second try so this is the best i can do for now
        while(True):
            try:
                state = await (await self._makeRequest("post", self.settingChangeState_url.format(self.http_url), data=requestBody)).text()
                break
            except:
                pass
        returnobj["state"] = self._translationTable["settingChangeStates"][state]

        return returnobj

    #uodate all existing settings Changes
    async def _updateAllsettingChangeStates(self):
        requestList = []

        #Limit state update requestes to every 10 seconds
        if(int(time.time()) < self._settingChangeState_lastUpdate + self._settingChangeState_rateLimitSeconds):
            return

        self._settingChangeState_lastUpdate = int(time.time())

        for deviceID in self._settingChangeState_list:
            for changeID in self._settingChangeState_list[deviceID]:
                if(self._settingChangeState_list[deviceID][changeID]["state"] == "completed"):
                    self._settingChangeState_list[deviceID].pop(f"{changeID}", None)
                    await self._fetchAvailableDeviceSettings()
                    break
                if(self._settingChangeState_list[deviceID][changeID]["state"] == "failed"):
                    try:
                        await self.changeSetting(deviceID=deviceID,settingName=self._settingChangeState_list[deviceID][changeID]["settingName"],targetValue=self._settingChangeState_list[deviceID][changeID]["targetValue"])
                        self._settingChangeState_list[deviceID][changeID]["state"] = "rescheduled"
                    except SettingAlreadyHasTargetValue:
                        print("Setting Already Has TargetValue")
                        self._settingChangeState_list[deviceID].pop(f"{changeID}", None)
                    break
                if(self._settingChangeState_list[deviceID][changeID]["state"] == "rescheduled"):
                    self._settingChangeState_list[deviceID].pop(f"{changeID}", None)
                    break
                requestList.append(asyncio.ensure_future(self._handleSettingChangeRequest(deviceID= deviceID, changeID= changeID)))

        requestResults = await asyncio.gather(*requestList)

        for res in requestResults:
            self._settingChangeState_list[res["deviceID"]][res["changeID"]]["state"] = res["state"]

    #get Current State of Settings Change
    async def getSettingChangeState(self, deviceNumber: int = None, changeID: int= None):
        if(self.initialized == False):
            raise ClientNotInitialized

        await self._updateAllsettingChangeStates()

        if(deviceNumber):
            if(changeID):
                return self._settingChangeState_list[deviceNumber][changeID]
            return self._settingChangeState_list[deviceNumber]
        
        return self._settingChangeState_list

    #generate a list of all available settings per device
    async def _fetchAvailableDeviceSettings(self):
        pattern = re.compile("[\w\d+]{1,}")

        for deviceID in self._devices.keys():

            self._availableSettings[deviceID] = {}

            html = BeautifulSoup(await (await self._makeRequest("get", url=self.deviceSettings_url.format(self.http_url, deviceID))).text(), "html.parser")
            selects = html.find_all("select")
            for select in selects:
                self._availableSettings[deviceID][select["name"]] = {}
                for child in select.children:
                    if(pattern.match(child.text)):
                        self._availableSettings[deviceID][select["name"]][child["value"]] = {}
                        self._availableSettings[deviceID][select["name"]][child["value"]]["name"] = child.text
                        if("selected" in child.attrs.keys()):
                            self._availableSettings[deviceID][select["name"]][child["value"]]["selected"] = True
                        else:
                            self._availableSettings[deviceID][select["name"]][child["value"]]["selected"] = False
                        
        self._availableSettings = await self._translateApiOutput(self._availableSettings)

    #provide a list of available settings
    async def getAvailableSettings(self, deviceID: int= None):
        if(self.initialized == False):
            raise ClientNotInitialized

        if(deviceID):
            return self._availableSettings[deviceID]

        return self._availableSettings
