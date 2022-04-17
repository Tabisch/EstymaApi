import json
from api import EstymaApi

credentials = json.load(open('credentials.json'))

apisession = EstymaApi(credentials["username"],credentials["password"])

for Device_Id in list(apisession.Devices.keys()):
    print(json.dumps(apisession.fetchDevicedata(Device_Id), indent=4))