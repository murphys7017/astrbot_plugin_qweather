# qweather_astrbot (AstrBot Plugin)

This repository is migrated from the openclaw-qweather skill to an AstrBot plugin with Python implementation.

## Features

- `weather` / `天气`: current weather (with Open-Meteo fallback)
- `forecast` / `预报`: daily forecast (3/7/15 days)
- `hourly` / `小时预报`: hourly forecast (24h/72h/168h)
- `rain` / `降水`: minutely precipitation
- `warning` / `预警`: weather warnings
- `indices` / `指数`: life indices
- Auto-detect weather queries from normal chat messages
- Multi-turn memory for follow-up queries (for example: \"What about tomorrow?\")

## Key Files

- `main.py`: AstrBot plugin entry
- `weather_plugin/service.py`: weather service logic
- `_conf_schema.json`: plugin config schema
- `metadata.yaml`: plugin metadata
- `requirements.txt`: dependencies
- `lib/ed25519-private.txt`: Ed25519 private key file (kept as-is)

## Install

```bash
pip install -r requirements.txt
```

## Commands

- `/weather Beijing` or `/天气 北京`
- `/forecast Shanghai 7` or `/预报 上海 7`
- `/hourly Guangzhou 72h` or `/小时预报 广州 72h`
- `/rain Hangzhou` or `/降水 杭州`
- `/warning Chengdu` or `/预警 成都`
- `/indices Nanjing 1d all` or `/指数 南京 1d all`

## Notes

- Python 3.10+
- Valid QWeather enterprise credentials and Ed25519 private key are required.
- Warning API uses `weatheralert/v1/current/{lat}/{lon}` and requires resolved coordinates.


