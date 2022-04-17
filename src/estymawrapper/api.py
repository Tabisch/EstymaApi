import json
import requests
import urllib.parse

class EstymaApi:

    http_url = "igneo.pl"

    def __init__(self, Username, Password):
        self.Username = urllib.parse.quote(Username)
        self.Password = urllib.parse.quote(Password)
        self.Devices = None
        
        self.headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        self.login_url = "https://{0}/login"
        self.update_url = "https://{0}/info_panel_update"
        self.devicelist_url = "https://{0}/main_panel/get_user_device_list"

        self.session = requests.Session()
        self.login()
        self.Devices = self.get_Devices()

    def login(self):
        data = "login={0}&haslo={1}&zaloguj=Login"
        dataformated = data.format(self.Username, self.Password)

        result = self.session.post(self.login_url.format(self.http_url),headers=self.headers, data=dataformated, allow_redirects=False)

        if(result.status_code == 200):
            raise Exception()

    def fetchDevicedata(self,Device_ID):

        data="id_urzadzenia={0}"

        #json_response = json.loads(self.session.post(self.update_url.format(self.http_url), headers=self.headers, data=data.format(Device_ID)).text)

        json_response = self.session.post(self.update_url.format(self.http_url), headers=self.headers, data=data.format(Device_ID)).text

        return self.translateApiOutput(json_response)

    def get_Devices(self):

        data = payload='sEcho=1&iColumns=8&sColumns=&iDisplayStart=0&iDisplayLength=5&mDataProp_0=0&mDataProp_1=1&mDataProp_2=2&mDataProp_3=3&mDataProp_4=4&mDataProp_5=5&mDataProp_6=6&mDataProp_7=7&sSearch=&bRegex=false&sSearch_0=&bRegex_0=false&bSearchable_0=true&sSearch_1=&bRegex_1=false&bSearchable_1=true&sSearch_2=&bRegex_2=false&bSearchable_2=true&sSearch_3=&bRegex_3=false&bSearchable_3=true&sSearch_4=&bRegex_4=false&bSearchable_4=true&sSearch_5=&bRegex_5=false&bSearchable_5=true&sSearch_6=&bRegex_6=false&bSearchable_6=true&sSearch_7=&bRegex_7=false&bSearchable_7=true&iSortingCols=1&iSortCol_0=0&sSortDir_0=asc&bSortable_0=true&bSortable_1=true&bSortable_2=true&bSortable_3=false&bSortable_4=false&bSortable_5=false&bSortable_6=false&bSortable_7=false&sByUserName='

        result = json.loads(self.session.post(self.devicelist_url.format(self.http_url),data=data , headers=self.headers).text)

        output_json = json.loads('{}')

        if(result["iTotalRecords"] > 0):
            counter = 0
            
            for device in result["devices_list"]:
                device_template = json.loads(f'{{"name": "{device["0"]}"}}')

                output_json[f'{device["id"]}'] = device_template

        return output_json

    def translateApiOutput(self,input):
        translationTable = json.load(open('api_translation_table.json'))

        translated_json = input

        for inputkey in list(translationTable.keys()):
            translated_json =  translated_json.replace(inputkey, translationTable[inputkey])

        #for inputkey in list(input.keys()):
        #    translated_json[translationTable[inputkey]] = input[inputkey]

        return json.loads(translated_json)
