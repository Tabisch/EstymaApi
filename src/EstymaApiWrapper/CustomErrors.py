class SettingNotAvailableException(Exception):
    print("The setting does not exist")

class SettingAlreadyHasTargetValue(Exception):
    print("Setting already has target value")

class ClientNotInitialized(Exception):
    print("Estyma API Client is not initialized")
    print("Initialize the client before using it")