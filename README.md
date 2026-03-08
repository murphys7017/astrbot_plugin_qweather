# qweather_astrbot (AstrBot 插件)

将原 openclaw-qweather Skill 改造为 AstrBot 插件，核心天气逻辑已迁移为 Python。

## 功能

- 实时天气 `weather/天气`（QWeather 失败时可回退 Open-Meteo）
- 日预报 `forecast/预报`（3/7/15 天）
- 逐小时预报 `hourly/小时预报`（24h/72h/168h）
- 分钟级降水 `rain/降水`
- 气象预警 `warning/预警`
- 生活指数 `indices/指数`
- 自动识别天气问句并回复（可配置开关和关键词）
- 多轮上下文记忆（支持“明天呢/后天呢/那呢”沿用上文地点）

## 插件结构

- `main.py` AstrBot 插件入口，命令、意图识别与多轮上下文
- `weather_plugin/service.py` 天气服务层（JWT、地理解析、QWeather/Open-Meteo 调用）
- `_conf_schema.json` AstrBot 配置定义
- `metadata.yaml` 插件元信息
- `requirements.txt` Python 依赖
- `lib/ed25519-private.txt` Ed25519 私钥文件（仅保留此文件）

## 安装依赖

```bash
pip install -r requirements.txt
```

## AstrBot 配置项

在 AstrBot 插件配置中填写：

- `api_host`: 你的企业 API Host（例如 `xxx.re.qweatherapi.com`）
- `project_id`: QWeather Project ID
- `credentials_id`: QWeather Credentials ID
- `private_key_path`: Ed25519 私钥绝对路径（部署服务器上）
- `private_key_pem`: Paste full PEM key content here. If set, it takes priority over `private_key_path`
- `default_location`: 默认位置（未传 location 时使用）
- `lang`: 返回语言（默认 `zh`）
- `unit`: 温度单位（`m` 公制 / `i` 英制）
- `warning_local_time`: 预警是否使用本地时间（`true/false`，默认 `false`）
- `openmeteo_fallback`: 实时天气失败时是否回退 Open-Meteo
- `auto_detect_enabled`: 是否自动识别天气提问
- `weather_keywords`: 自动识别时使用的关键词列表

## 命令用法

- `/weather 北京` 或 `/天气 北京`
- `/forecast 上海 7` 或 `/预报 上海 7`
- `/hourly 广州 72h` 或 `/小时预报 广州 72h`
- `/rain 杭州` 或 `/降水 杭州`
- `/warning 成都` 或 `/预警 成都`
- `/indices 南京 1d all` 或 `/指数 南京 1d all`

## 自动识别天气提问

开启 `auto_detect_enabled=true` 后，普通消息中包含关键词（如“天气”“气温”“下雨”“预报”）会自动触发对应查询。

位置提取规则为轻量正则匹配（如“北京天气怎么样”），若未提取到地点则回退到 `default_location`。

同一会话会记忆最近地点，支持“明天呢”“后天呢”“那呢”这类追问。

## 注意

- 需要 Python 3.10+。
- QWeather 企业 API 必须配置正确的 Ed25519 私钥。
- 预警接口使用 `weatheralert/v1/current/{lat}/{lon}`，依赖地点解析出经纬度。


