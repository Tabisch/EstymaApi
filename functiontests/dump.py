    f = open("dump_data.txt", "w")
    f.write(json.dumps(await api.getDeviceData(), indent=4))
    f.close()

    f = open("dump_data_textToValues.txt", "w")
    f.write(json.dumps(await api.getDeviceData(textToValues=True), indent=4))
    f.close()

    f = open("dump_settings.txt", "w")
    f.write(json.dumps(await api.getAvailableSettings(), indent=4))
    f.close()