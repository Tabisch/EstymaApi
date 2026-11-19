import json
import urllib.parse
import aiohttp
import asyncio
import time
import datetime
import importlib.resources
from bs4 import BeautifulSoup
import re
from .CustomErrors import SettingNotAvailableException, SettingAlreadyHasTargetValue, ClientNotInitialized, StatisticsNotAvailable

class EstymaApi:
    login_url = "https://{0}/login"
    logout_url = "https://{0}/logout"
    deviceSettings_url = "https://{0}/device/{1}"
    update_url = "https://{0}/info_panel_update"
    changeSetting_url = "https://{0}/info_set_order"
    settingChangeState_url = "https://{0}/info_check_order"
    devicelist_url = "https://{0}/main_panel/get_user_device_list"
    statistics_url = "https://{0}/line-chart"
    fuelStatistics_url = "https://{0}/chart-fuel"
    statisticsPage_url = "https://{0}/device/{1}/chart"

    languageSwitch_url = "https://{0}/switchLanguage/{1}}"
    
    headers = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
    fetchDevicedataBody = "id_urzadzenia={0}"
    loginDataBody = "login={0}&haslo={1}&zaloguj=Login"
    changeSettingBody = "id_urzadzenia={0}&name={1}&value={2}"
    settingChangeStateBody = "id_urzadzenia={0}&order_number={1}"
    statisticsBody = "id_urzadzenia={0}&accuracy={1}&dp_from={2}&dp_to={3}&show_burner_status={4}"

    fuelStatisticsBody = "id_urzadzenia={0}&year={1}&month={2}"

    statisticsDateFormat = "%d-%m-%Y"
    statisticsUnitRegex = r"\(([^)]*)\)\s*$"
    statisticsDatepickerRegex = r"\.{0}\"\s*\)\.datepicker\(\{{(.*?)\}}\);"
    statisticsMinDateRegex = r"minDate:\s*'-(\d+)([DWMY])'"
    statisticsMaxDateRegex = r"maxDate:\s*new Date\((\d+)\)"
    statisticsMaxRangeRegex = r"dtMax\.setDate\(dtMax\.getDate\(\)\s*\+\s*(\d+)\)"

    updateDiffRegex = r"(\d+)d (\d+)h:(\d+)m:(\d+)s"

    def __init__(self,Email: str, Password: str,Domain: str = "igneo.pl" , scanInterval = 30, language: str = "english", staleDataThresholdSeconds: int = 300):
        self._http_url = Domain
        
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
        self._deviceDataValues = "{}"
        self._settingUpdatingTable = json.loads("{}")

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

        self._statisticsLimits = {}
        self._statisticsLimits_cacheSeconds = 3600

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
            await self._fetchAvailableDeviceSettings()
            await self._fetchDevicedata()
            self._settingUpdatingTable = await self._createSettingsUpdateTable()
        except Exception as e:
            #print(e)
            if(throw_Execetion):
                raise Exception

        return self.initialized

    #login to Api
    async def _login(self):
        self._session = aiohttp.ClientSession()

        dataformated = self.loginDataBody.format(self._Email, self._Password)

        result = (await self._makeRequest("post", self.login_url.format(self._http_url), data=dataformated)).status

        if(result == 302):
            self._initialized = True
            self._loggedIn = True
            self._loginTime = int(time.time())
            return

        raise Exception

    async def _logout(self):
        self._loggedIn = False

        try:
            if((await self._makeRequest("get", self.logout_url.format(self._http_url))).status == 302):
                await self._session.close()
                return
        except:
            return
        
        return
    
    async def testCredentials(self):
        result = False

        try:
            await self._login()
            await self._logout()
            result = True
        except:
            await self._session.close()

        return result

    async def _relog(self):
        try:
            await self._logout()
            await self._login()
            await self.switchLanguage(self._language)
        except:
            return

    #fetch data for all devices
    async def _fetchDevicedatatask(self, deviceid):
        resp = await (await self._makeRequest("post", self.update_url.format(self._http_url), data=self.fetchDevicedataBody.format(deviceid))).json(content_type='text/html')
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

        self._deviceDataValues = json.dumps(await self._dataTextToValues(json.loads(self._deviceData)))

    async def _createSettingsUpdateTable(self):
        settingUpdatingTable = {}

        for deviceId in self._availableSettings.keys():
            settingUpdatingTable[deviceId] = {}
            for setting in self._availableSettings[deviceId].keys():
                settingUpdatingTable[deviceId][setting] = False

        return settingUpdatingTable

    async def getDevices(self):
        if(self.initialized == False):
            raise ClientNotInitialized("Estyma API Client is not initialized")

        return self._devices

    #get data for device\devices
    async def getDeviceData(self, DeviceID = None, textToValues: bool = False):
        if(self.initialized == False):
            raise ClientNotInitialized("Estyma API Client is not initialized")

        if((int(time.time()) - self._scanInterval) > self._lastUpdated):
            if(self._updatingdata == False):
                try:
                    await self._fetchDevicedata()
                except:
                    await self._relog()
                    self._updatingdata = False
                    #print("getDeviceData except. Delivering previous data.")

        data = ""

        if textToValues:
            data = json.loads(self._deviceDataValues)
        else:
            data = json.loads(self._deviceData)

        if(DeviceID == None):
            return data

        return data[f'{DeviceID}']

    async def _fetchDevices(self):
        #could be optimised maybe
        #ripped this stright from the brup suite, works for now
        data = 'sEcho=1&iColumns=8&sColumns=&iDisplayStart=0&iDisplayLength=5&mDataProp_0=0&mDataProp_1=1&mDataProp_2=2&mDataProp_3=3&mDataProp_4=4&mDataProp_5=5&mDataProp_6=6&mDataProp_7=7&sSearch=&bRegex=false&sSearch_0=&bRegex_0=false&bSearchable_0=true&sSearch_1=&bRegex_1=false&bSearchable_1=true&sSearch_2=&bRegex_2=false&bSearchable_2=true&sSearch_3=&bRegex_3=false&bSearchable_3=true&sSearch_4=&bRegex_4=false&bSearchable_4=true&sSearch_5=&bRegex_5=false&bSearchable_5=true&sSearch_6=&bRegex_6=false&bSearchable_6=true&sSearch_7=&bRegex_7=false&bSearchable_7=true&iSortingCols=1&iSortCol_0=0&sSortDir_0=asc&bSortable_0=true&bSortable_1=true&bSortable_2=true&bSortable_3=false&bSortable_4=false&bSortable_5=false&bSortable_6=false&bSortable_7=false&sByUserName='

        result = await (await self._makeRequest("post", self.devicelist_url.format(self._http_url),data=data)).json(content_type='text/html')

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
    
    async def _dataTextToValues(self,data: dict):
        deviceSettings = await self.getAvailableSettings()

        for device in data.keys():
            for setting in data[device].keys():

                if setting in deviceSettings[device].keys():

                    for value in deviceSettings[device][setting].keys():
                        if deviceSettings[device][setting][value]["name"] == data[device][setting]:
                            data[device][setting] = int(value)

        return data

    async def switchLanguage(self, targetLanguage: str):
        if(self.initialized == False):
            raise ClientNotInitialized("Estyma API Client is not initialized")

        languageTable = None

        with importlib.resources.open_text("EstymaApiWrapper", 'languageTable.json') as file:
            languageTable = json.load(file)

        url = self.login_url.format(self._http_url, languageTable[targetLanguage.lower()])

        await self._makeRequest("get", url)

    #send request to change a Setting
    async def changeSetting(self, deviceID: int, settingName: str, targetValue: int):
        if(self.initialized == False):
            raise ClientNotInitialized("Estyma API Client is not initialized")

        if((await self.getDeviceData(deviceID, textToValues=True))[settingName] == targetValue):
            raise SettingAlreadyHasTargetValue("Setting already has target value")

        if(str(targetValue) not in self._availableSettings[f"{deviceID}"][settingName].keys()):
            raise SettingNotAvailableException("The setting does not exist")
        
        settingNameTranslated = ""
        for key, value in self._translationTable["deviceState"].items():
             if value == settingName:
                settingNameTranslated = key

        dataBody = self.changeSettingBody.format(deviceID, settingNameTranslated, targetValue)

        url = self.changeSetting_url.format(self._http_url)

        changeID = await (await self._makeRequest("post", url, data=dataBody)).text()

        #create key for device if does not exist
        if(deviceID not in self._settingChangeState_list):
            self._settingChangeState_list[deviceID] = {}

        #create key for stateChange if does not exist
        self._settingChangeState_list[deviceID][changeID] = {}

        self._settingChangeState_list[deviceID][changeID]["settingName"] = settingName
        self._settingChangeState_list[deviceID][changeID]["targetValue"] = targetValue
        self._settingChangeState_list[deviceID][changeID]["state"] = ""

        self._settingUpdatingTable[deviceID][settingName] = True

    async def _handleSettingChangeRequest(self,deviceID: int, changeID: int):
        requestBody=self.settingChangeStateBody.format(deviceID, changeID)

        returnobj = {}
        returnobj["deviceID"] = deviceID
        returnobj["changeID"] = changeID

        state = ""

        #idk why but the request seam to fail like every second try so this is the best i can do for now
        while(True):
            try:
                state = await (await self._makeRequest("post", self.settingChangeState_url.format(self._http_url), data=requestBody)).text()
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
                    #await self._fetchAvailableDeviceSettings()
                    break
                if(self._settingChangeState_list[deviceID][changeID]["state"] == "failed"):
                    try:
                        await self.changeSetting(deviceID=deviceID,settingName=self._settingChangeState_list[deviceID][changeID]["settingName"],targetValue=self._settingChangeState_list[deviceID][changeID]["targetValue"])
                        self._settingChangeState_list[deviceID][changeID]["state"] = "rescheduled"
                    except SettingAlreadyHasTargetValue:
                        #print("Setting Already Has TargetValue")
                        self._settingChangeState_list[deviceID].pop(f"{changeID}", None)
                    break
                if(self._settingChangeState_list[deviceID][changeID]["state"] == "rescheduled"):
                    self._settingChangeState_list[deviceID].pop(f"{changeID}", None)
                    break
                requestList.append(asyncio.ensure_future(self._handleSettingChangeRequest(deviceID= deviceID, changeID= changeID)))

        requestResults = await asyncio.gather(*requestList)

        settingUpdatingTable = await self._createSettingsUpdateTable()

        for res in requestResults:
            self._settingChangeState_list[res["deviceID"]][res["changeID"]]["state"] = res["state"]
            settingUpdatingTable[f"{res["deviceID"]}"][self._settingChangeState_list[res["deviceID"]][res["changeID"]]["settingName"]] = True

        self._settingUpdatingTable = settingUpdatingTable

    #get Current State of Settings Change
    async def getSettingChangeState(self, deviceNumber: int = None, changeID: int= None):
        if(self.initialized == False):
            raise ClientNotInitialized("Estyma API Client is not initialized")

        await self._updateAllsettingChangeStates()

        if(deviceNumber):
            if(changeID):
                return self._settingChangeState_list[deviceNumber][changeID]
            return self._settingChangeState_list[deviceNumber]
        
        return self._settingChangeState_list

    #generate a list of all available settings per device
    async def _fetchAvailableDeviceSettings(self):
        pattern = re.compile(r"[\w\d+]{1,}")

        for deviceID in self._devices.keys():

            self._availableSettings[deviceID] = {}

            html = BeautifulSoup(await (await self._makeRequest("get", url=self.deviceSettings_url.format(self._http_url, deviceID))).text(), "html.parser")
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
            raise ClientNotInitialized("Estyma API Client is not initialized")

        if(deviceID):
            return self._availableSettings[deviceID]

        return self._availableSettings
    
    async def isUpdating(self, deviceID:int, settingName:str = ""):
        await self.getSettingChangeState()

        if deviceID in self._settingChangeState_list.keys() and len(settingName) == 0:
            if len(self._settingChangeState_list[deviceID].keys()) != 0:
                return True

        return self._settingUpdatingTable[deviceID][settingName]
    
    async def getUpdatingSettingTable(self):
        await self._updateAllsettingChangeStates()

        return self._settingUpdatingTable

    #convert date input for the statistics request to the DD-MM-YYYY format the api expects
    def _formatStatisticsDate(self, value):
        if(value is None):
            return "0"

        if(isinstance(value, (datetime.date, datetime.datetime))):
            return value.strftime(self.statisticsDateFormat)

        return str(value)

    #download raw statistics (line chart) data for a device
    async def _fetchStatistics(self, deviceID, dateFrom = None, dateTo = None, accuracy: int = 0, showBurnerStatus: bool = False):
        if((int(time.time()) - self._loginTimeLimit) > self._loginTime):
            await self._relog()

        if(dateTo is None):
            dateTo = datetime.date.today()

        dataBody = self.statisticsBody.format(
            deviceID,
            accuracy,
            self._formatStatisticsDate(dateFrom),
            self._formatStatisticsDate(dateTo),
            str(showBurnerStatus).lower()
        )

        response = await self._makeRequest("post", self.statistics_url.format(self._http_url), data=dataBody)

        #api answers with content type text/html, so parse the body manually
        return json.loads(await response.text())

    #turn the raw line chart series list into a dict keyed by (translated) series id
    async def _parseStatistics(self, series: list, translateData: bool = True):
        output = {}

        for entry in series:
            apiID = entry.get("id")
            seriesID = apiID

            if(translateData):
                seriesID = self._translationTable["deviceState"].get(apiID, apiID)

            name = str(entry.get("name", "")).strip()
            unitMatch = re.search(self.statisticsUnitRegex, name)

            parsed = {}
            parsed["id"] = seriesID
            parsed["api_id"] = apiID
            parsed["name"] = name
            parsed["unit"] = unitMatch.group(1).strip() if unitMatch else None
            parsed["visible"] = entry.get("visible")
            parsed["legendIndex"] = entry.get("legendIndex")
            parsed["from"] = entry.get("FROM")
            parsed["to"] = entry.get("TO")
            #timestamps from the api are epoch milliseconds, convert to epoch seconds
            parsed["data"] = [{"timestamp": int(point[0] / 1000), "value": point[1]} for point in entry.get("data", [])]

            output[seriesID] = parsed

        return output

    #get statistics (line chart) data for a device
    #dateFrom/dateTo accept datetime.date objects or "DD-MM-YYYY" strings
    #without dateFrom the api returns the single day given by dateTo (defaults to today)
    #with validate the requested range is checked against getStatisticsLimits first
    async def getStatistics(self, deviceID, dateFrom = None, dateTo = None, accuracy: int = 0, showBurnerStatus: bool = False, translateData: bool = True, raw: bool = False, validate: bool = True):
        if(self.initialized == False):
            raise ClientNotInitialized("Estyma API Client is not initialized")

        if(validate):
            await self._validateStatisticsRange(deviceID, dateFrom, dateTo)

        try:
            series = await self._fetchStatistics(deviceID, dateFrom, dateTo, accuracy, showBurnerStatus)
        except Exception:
            #session might have expired, retry once after logging in again
            await self._relog()
            series = await self._fetchStatistics(deviceID, dateFrom, dateTo, accuracy, showBurnerStatus)

        if(raw):
            return series

        return await self._parseStatistics(series, translateData)

    #convert numbers like "1,320.30" or "0.9" from the api to float
    def _parseApiNumber(self, value):
        if(value is None):
            return None

        if(isinstance(value, (int, float))):
            return value

        try:
            return float(str(value).replace(",", ""))
        except ValueError:
            return None

    #download raw fuel consumption statistics for a device
    async def _fetchFuelStatistics(self, deviceID, year: int, month: int):
        if((int(time.time()) - self._loginTimeLimit) > self._loginTime):
            await self._relog()

        dataBody = self.fuelStatisticsBody.format(deviceID, year, month)

        response = await self._makeRequest("post", self.fuelStatistics_url.format(self._http_url), data=dataBody)

        #api answers with content type text/html, so parse the body manually
        return json.loads(await response.text())

    #turn the raw fuel chart response into a flat dict with one entry per day (or per month for month 0)
    async def _parseFuelStatistics(self, series: list, year: int, month: int):
        fuelSeries = next((entry for entry in series if entry.get("name") == "fuel"), series[0] if series else {})

        output = {}
        output["year"] = year
        output["month"] = month
        output["data"] = []

        #for a single month the entries are days, for the whole year (month 0) they are months
        periodKey = "month" if int(month) == 0 else "day"

        for point in fuelSeries.get("data", []):
            parsed = {}
            parsed[periodKey] = point.get("name")
            parsed["fuel"] = point.get("y")
            parsed["price"] = self._parseApiNumber(point.get("stawka"))
            parsed["cost"] = self._parseApiNumber(point.get("koszt"))
            parsed["currency"] = point.get("waluta")

            output["data"].append(parsed)

        output["fuel_total"] = sum((point["fuel"] or 0) for point in output["data"])
        output["cost_total"] = self._parseApiNumber(fuelSeries.get("total_cost"))
        output["cost_total_by_currency"] = {currency: self._parseApiNumber(value) for currency, value in (fuelSeries.get("total_cost2") or {}).items()}
        output["currency"] = next((point["currency"] for point in output["data"] if point["currency"]), None)

        return output

    #get fuel consumption statistics of a device for one month (defaults to the current month)
    #month 0 returns the whole year with one entry per month
    async def getFuelStatistics(self, deviceID, year: int = None, month: int = None, raw: bool = False, validate: bool = True):
        if(self.initialized == False):
            raise ClientNotInitialized("Estyma API Client is not initialized")

        today = datetime.date.today()

        if(year is None):
            year = today.year

        if(month is None):
            month = today.month

        if(validate):
            limits = (await self.getStatisticsLimits(deviceID))["fuelStatistics"]

            if(limits["years"] and int(year) not in limits["years"]):
                raise StatisticsNotAvailable(f"No fuel statistics for year {year}, available: {limits['years']}")

            if(limits["months"] and int(month) not in limits["months"]):
                raise StatisticsNotAvailable(f"Month {month} is not available, available: {list(limits['months'].keys())}")

        try:
            series = await self._fetchFuelStatistics(deviceID, year, month)
        except Exception:
            #session might have expired, retry once after logging in again
            await self._relog()
            series = await self._fetchFuelStatistics(deviceID, year, month)

        if(raw):
            return series

        return await self._parseFuelStatistics(series, year, month)

    #subtract an amount of days/weeks/months/years like the jquery datepicker does for '-4M'
    def _subtractDatepickerOffset(self, date: datetime.date, amount: int, unit: str):
        if(unit == "D"):
            return date - datetime.timedelta(days=amount)

        if(unit == "W"):
            return date - datetime.timedelta(weeks=amount)

        months = amount * 12 if unit == "Y" else amount
        totalMonths = date.year * 12 + (date.month - 1) - months
        year = totalMonths // 12
        month = totalMonths % 12 + 1

        #clamp the day for shorter months (e.g. 31st -> 30th)
        nextMonth = datetime.date(year + (month // 12), month % 12 + 1, 1)
        lastDay = (nextMonth - datetime.timedelta(days=1)).day

        return datetime.date(year, month, min(date.day, lastDay))

    #read the min/max date of one of the datepickers on the chart page
    def _parseDatepickerLimits(self, scripts: str, className: str, today: datetime.date):
        limits = {"min": None, "max": None}

        datepicker = re.search(self.statisticsDatepickerRegex.format(re.escape(className)), scripts, re.DOTALL)

        if(datepicker is None):
            return limits

        minDate = re.search(self.statisticsMinDateRegex, datepicker.group(1))
        if(minDate):
            limits["min"] = self._subtractDatepickerOffset(today, int(minDate.group(1)), minDate.group(2))

        maxDate = re.search(self.statisticsMaxDateRegex, datepicker.group(1))
        if(maxDate):
            limits["max"] = datetime.datetime.fromtimestamp(int(maxDate.group(1)) / 1000).date()

        return limits

    #read the options of a select on the chart page as {value: text}
    def _parseSelectOptions(self, html: BeautifulSoup, selectID: str):
        options = {}

        select = html.find("select", id=selectID)

        if(select is None):
            return options

        for option in select.find_all("option"):
            options[int(option["value"])] = option.text.strip()

        return options

    #parse the chart page of a device to find out which statistics are available
    async def _parseStatisticsLimits(self, page: str):
        html = BeautifulSoup(page, "html.parser")
        scripts = "\n".join(script.get_text() for script in html.find_all("script"))
        today = datetime.date.today()

        dateFrom = self._parseDatepickerLimits(scripts, "dp_from", today)
        dateTo = self._parseDatepickerLimits(scripts, "dp_to", today)

        maxRange = re.search(self.statisticsMaxRangeRegex, scripts)

        limits = {}

        limits["statistics"] = {}
        limits["statistics"]["dateFrom_min"] = dateFrom["min"]
        limits["statistics"]["dateFrom_max"] = dateFrom["max"]
        limits["statistics"]["dateTo_min"] = dateTo["min"]
        limits["statistics"]["dateTo_max"] = dateTo["max"]
        limits["statistics"]["maxRangeDays"] = int(maxRange.group(1)) if maxRange else None
        limits["statistics"]["accuracy"] = self._parseSelectOptions(html, "chart_accuracy")

        limits["fuelStatistics"] = {}
        limits["fuelStatistics"]["years"] = sorted(self._parseSelectOptions(html, "chart-fuel-year").keys())
        limits["fuelStatistics"]["months"] = self._parseSelectOptions(html, "chart-fuel-month")

        return limits

    #get the limits of the statistics a device provides, read from its chart page
    #dates are datetime.date objects, cached for an hour per device
    async def getStatisticsLimits(self, deviceID, forceRefresh: bool = False):
        if(self.initialized == False):
            raise ClientNotInitialized("Estyma API Client is not initialized")

        cached = self._statisticsLimits.get(f"{deviceID}")

        if(cached and not forceRefresh and (int(time.time()) - cached["fetched"]) < self._statisticsLimits_cacheSeconds):
            return cached["limits"]

        if((int(time.time()) - self._loginTimeLimit) > self._loginTime):
            await self._relog()

        page = await (await self._makeRequest("get", self.statisticsPage_url.format(self._http_url, deviceID))).text()

        limits = await self._parseStatisticsLimits(page)

        self._statisticsLimits[f"{deviceID}"] = {"fetched": int(time.time()), "limits": limits}

        return limits

    #convert statistics date input to datetime.date
    def _toStatisticsDate(self, value):
        if(value is None):
            return None

        if(isinstance(value, datetime.datetime)):
            return value.date()

        if(isinstance(value, datetime.date)):
            return value

        return datetime.datetime.strptime(str(value), self.statisticsDateFormat).date()

    #raise StatisticsNotAvailable if the requested range is outside of what the device provides
    async def _validateStatisticsRange(self, deviceID, dateFrom, dateTo):
        limits = (await self.getStatisticsLimits(deviceID))["statistics"]

        dateFrom = self._toStatisticsDate(dateFrom)
        dateTo = self._toStatisticsDate(dateTo) or datetime.date.today()

        if(limits["dateTo_max"] and dateTo > limits["dateTo_max"]):
            raise StatisticsNotAvailable(f"dateTo {dateTo} is after the newest available data {limits['dateTo_max']}")

        if(limits["dateTo_min"] and dateTo < limits["dateTo_min"]):
            raise StatisticsNotAvailable(f"dateTo {dateTo} is before the oldest available data {limits['dateTo_min']}")

        if(dateFrom is None):
            return

        if(limits["dateFrom_min"] and dateFrom < limits["dateFrom_min"]):
            raise StatisticsNotAvailable(f"dateFrom {dateFrom} is before the oldest available range start {limits['dateFrom_min']}")

        if(dateFrom > dateTo):
            raise StatisticsNotAvailable(f"dateFrom {dateFrom} is after dateTo {dateTo}")

        if(limits["maxRangeDays"] and (dateTo - dateFrom).days > limits["maxRangeDays"]):
            raise StatisticsNotAvailable(f"The range {dateFrom} - {dateTo} is longer than {limits['maxRangeDays']} days")
