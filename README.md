Wrapper for the Estyma Heating Systems. \
Igneo.pl and bia24.net are both work.

The wrapper ist primarily build to integrate our heating system into home assistant.

https://github.com/Tabisch/Igneo_ha_integration


## Statistics

Download the statistics (line chart) data of a device:

```python
import datetime

stats = await api.getStatistics(deviceID)                                  # today
stats = await api.getStatistics(deviceID, dateTo=datetime.date(2026, 11, 18))  # a specific day
stats = await api.getStatistics(deviceID, dateFrom="01-11-2026", dateTo="19-11-2026")

stats["temp_boiler_sub1"]["data"]  # [{"timestamp": <epoch seconds>, "value": 69.3}, ...]
```

Each series is keyed by its translated id and contains `name`, `unit`, `visible`, `from`, `to` and `data`.
Pass `translateData=False` to keep the original api ids, or `raw=True` to get the unmodified api response.
