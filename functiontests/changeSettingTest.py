    try:
        await api.changeSetting(4251681784, "status_controller_sub1", 1)
    except:
        await api.changeSetting(4251681784, "status_controller_sub1", 0)

    try:
        await api.changeSetting(4251681784, "temp_boiler_target_sub1", 61)
    except:
        await api.changeSetting(4251681784, "temp_boiler_target_sub1", 60)

    while await api.isUpdating(4251681784, "temp_boiler_target_sub1"):
        print(await api.getSettingChangeState())
        time.sleep(10)