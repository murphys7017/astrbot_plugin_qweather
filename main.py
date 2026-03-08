from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

try:
    from weather_plugin import WeatherService
    from weather_plugin.service import WeatherConfig
except ModuleNotFoundError:
    plugin_dir = Path(__file__).resolve().parent
    if str(plugin_dir) not in sys.path:
        sys.path.insert(0, str(plugin_dir))
    from weather_plugin import WeatherService
    from weather_plugin.service import WeatherConfig


@register(
    "qweather_astrbot",
    "openclaw",
    "和风天气插件（QWeather + Open-Meteo回退）",
    "1.0.0",
    "https://github.com/murphys7017/astrbot_plugin_qweather.git",
)
class QWeatherPlugin(Star):
    def __init__(self, context: Context, config: Dict[str, Any] | None = None):
        super().__init__(context)
        self.config = config or {}
        self.service = WeatherService(self._build_cfg(), Path(__file__).parent)
        self.keywords = self._load_keywords()
        self._session_memory: dict[str, dict[str, Any]] = {}

    @filter.command("weather")
    @filter.command("天气")
    async def cmd_weather(self, event: AstrMessageEvent, location: str = ""):
        event.stop_event()
        loc = location or self._get_session_location(event)
        data = await self.service.weather_now(loc or None)
        self._remember_context(event, self._resolve_location_name(data, loc), "now")
        yield event.plain_result(self._format_now(data))

    @filter.command("forecast")
    @filter.command("预报")
    async def cmd_forecast(self, event: AstrMessageEvent, location: str = "", days: int = 3):
        event.stop_event()
        loc = location or self._get_session_location(event)
        data = await self.service.weather_forecast(loc or None, days=days)
        self._remember_context(event, self._resolve_location_name(data, loc), "forecast")
        yield event.plain_result(self._format_forecast(data))

    @filter.command("hourly")
    @filter.command("小时预报")
    async def cmd_hourly(self, event: AstrMessageEvent, location: str = "", hours: str = "24h"):
        event.stop_event()
        loc = location or self._get_session_location(event)
        data = await self.service.weather_hourly(loc or None, hours=hours)
        self._remember_context(event, self._resolve_location_name(data, loc), "hourly")
        yield event.plain_result(self._format_hourly(data))

    @filter.command("rain")
    @filter.command("降水")
    async def cmd_rain(self, event: AstrMessageEvent, location: str = ""):
        event.stop_event()
        loc = location or self._get_session_location(event)
        data = await self.service.weather_minutely_precipitation(loc or None)
        self._remember_context(event, self._resolve_location_name(data, loc), "rain")
        yield event.plain_result(self._format_rain(data))

    @filter.command("warning")
    @filter.command("预警")
    async def cmd_warning(self, event: AstrMessageEvent, location: str = ""):
        event.stop_event()
        loc = location or self._get_session_location(event)
        data = await self.service.weather_warning(loc or None)
        self._remember_context(event, self._resolve_location_name(data, loc), "warning")
        yield event.plain_result(self._format_warning(data))

    @filter.command("indices")
    @filter.command("指数")
    async def cmd_indices(self, event: AstrMessageEvent, location: str = "", days: str = "1d", index_type: str = "all"):
        event.stop_event()
        loc = location or self._get_session_location(event)
        data = await self.service.weather_indices(loc or None, days=days, index_type=index_type)
        self._remember_context(event, self._resolve_location_name(data, loc), "indices")
        yield event.plain_result(self._format_indices(data))

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def auto_weather_detect(self, event: AstrMessageEvent):
        if not self.config.get("auto_detect_enabled", True):
            return

        msg = self._extract_text(event)
        if not msg:
            return

        if msg.startswith("/"):
            return

        intent = self._detect_intent(msg)
        follow_up = self._is_follow_up_query(msg)
        if not intent and not follow_up and not self._is_weather_query(msg):
            return

        location = self._extract_location(msg) or self._get_session_location(event)
        event.stop_event()

        if follow_up and not self._is_weather_query(msg):
            reply = await self._handle_follow_up(event, msg, location)
            if reply:
                yield event.plain_result(reply)
            return

        intent = intent or "now"
        if intent == "warning":
            data = await self.service.weather_warning(location)
            self._remember_context(event, self._resolve_location_name(data, location), "warning")
            yield event.plain_result(self._format_warning(data))
            return
        if intent == "rain":
            data = await self.service.weather_minutely_precipitation(location)
            self._remember_context(event, self._resolve_location_name(data, location), "rain")
            yield event.plain_result(self._format_rain(data))
            return
        if intent == "indices":
            data = await self.service.weather_indices(location, days="1d", index_type="all")
            self._remember_context(event, self._resolve_location_name(data, location), "indices")
            yield event.plain_result(self._format_indices(data))
            return
        if intent == "hourly":
            data = await self.service.weather_hourly(location, hours="24h")
            self._remember_context(event, self._resolve_location_name(data, location), "hourly")
            yield event.plain_result(self._format_hourly(data))
            return
        if intent == "forecast":
            days = self._days_from_text(msg)
            data = await self.service.weather_forecast(location, days=days)
            self._remember_context(event, self._resolve_location_name(data, location), "forecast")
            yield event.plain_result(self._format_forecast(data))
            return

        data = await self.service.weather_now(location)
        self._remember_context(event, self._resolve_location_name(data, location), "now")
        yield event.plain_result(self._format_now(data))

    def _build_cfg(self) -> WeatherConfig:
        return WeatherConfig(
            api_host=self.config.get("api_host", "xxx.re.qweatherapi.com"),
            project_id=self.config.get("project_id", ""),
            credentials_id=self.config.get("credentials_id", ""),
            private_key_path=self.config.get("private_key_path", "/home/aki/key/ed25519-private.pem"),
            private_key_pem=self.config.get("private_key_pem", ""),
            default_location=self.config.get("default_location", "北京"),
            lang=self.config.get("lang", "zh"),
            unit=self.config.get("unit", "m"),
            warning_local_time=self._to_bool(self.config.get("warning_local_time", False)),
            timeout_seconds=int(self.config.get("timeout_seconds", 15)),
            openmeteo_fallback=bool(self.config.get("openmeteo_fallback", True)),
        )

    def _load_keywords(self) -> list[str]:
        cfg_keywords = self.config.get("weather_keywords")
        if isinstance(cfg_keywords, list) and cfg_keywords:
            return [str(x).strip() for x in cfg_keywords if str(x).strip()]
        return [
            "天气",
            "气温",
            "温度",
            "下雨",
            "降雨",
            "降水",
            "会下雨吗",
            "weather",
            "forecast",
            "预报",
            "明天",
            "后天",
            "小时",
            "预警",
            "指数",
        ]

    def _is_weather_query(self, text: str) -> bool:
        lower = text.lower()
        return any(k.lower() in lower for k in self.keywords)

    def _extract_text(self, event: AstrMessageEvent) -> str:
        try:
            return event.message_str.strip()
        except Exception:
            try:
                return event.get_message_str().strip()
            except Exception:
                return ""

    def _extract_location(self, text: str) -> Optional[str]:
        patterns = [
            r"(?P<loc>[\u4e00-\u9fffA-Za-z]{2,20})(?:天气|气温|温度|会下雨吗|有雨吗)",
            r"(?:在|去|到)(?P<loc>[\u4e00-\u9fffA-Za-z]{2,20})(?:天气|气温|温度)?",
            r"weather\s+(?:in\s+)?(?P<loc>[A-Za-z\s]{2,40})",
        ]
        for p in patterns:
            match = re.search(p, text, flags=re.IGNORECASE)
            if match:
                loc = match.group("loc").strip()
                if loc:
                    return loc
        return None

    def _detect_intent(self, text: str) -> Optional[str]:
        lower = text.lower()
        if any(k in text for k in ["预警", "警报", "灾害"]):
            return "warning"
        if any(k in text for k in ["降水", "几分钟后下雨", "雨量", "雨势"]):
            return "rain"
        if any(k in text for k in ["指数", "穿衣", "洗车", "紫外线"]):
            return "indices"
        if any(k in text for k in ["小时", "每小时"]):
            return "hourly"
        if any(k in text for k in ["预报", "明天", "后天", "未来", "本周"]) or "forecast" in lower:
            return "forecast"
        if any(k in text for k in ["天气", "气温", "温度", "下雨"]) or "weather" in lower:
            return "now"
        return None

    def _days_from_text(self, text: str) -> int:
        match = re.search(r"(\d{1,2})\s*天", text)
        if match:
            return max(1, min(15, int(match.group(1))))
        if "后天" in text:
            return 3
        if "明天" in text:
            return 2
        if "本周" in text or "一周" in text:
            return 7
        return 3

    def _is_follow_up_query(self, text: str) -> bool:
        text = text.strip()
        markers = {"明天呢", "后天呢", "大后天呢", "那明天呢", "那后天呢", "那今天呢", "那呢", "然后呢"}
        if text in markers:
            return True
        return bool(re.fullmatch(r"(那)?(今天|明天|后天|大后天)(呢|怎么样|如何|会下雨吗)?", text))

    async def _handle_follow_up(self, event: AstrMessageEvent, text: str, location: Optional[str]) -> Optional[str]:
        if not location:
            return None
        if "明天" in text or "后天" in text or "大后天" in text:
            forecast = await self.service.weather_forecast(location, days=4)
            self._remember_context(event, self._resolve_location_name(forecast, location), "forecast")
            if not forecast.get("success"):
                return self._format_forecast(forecast)
            idx = 1 if "明天" in text else 2 if "后天" in text else 3
            daily = forecast.get("forecast", [])
            if len(daily) <= idx:
                return self._format_forecast(forecast)
            item = daily[idx]
            return (
                f"{forecast.get('location')} {item.get('date')} 天气\n"
                f"{item.get('textDay')} / {item.get('textNight')}\n"
                f"温度: {item.get('tempMin')}~{item.get('tempMax')}°C\n"
                f"来源: {forecast.get('source')}"
            )
        data = await self.service.weather_now(location)
        self._remember_context(event, self._resolve_location_name(data, location), "now")
        return self._format_now(data)

    def _session_key(self, event: AstrMessageEvent) -> str:
        for attr in ["session_id", "conversation_id", "group_id", "channel_id"]:
            value = getattr(event, attr, None)
            if value:
                return f"{attr}:{value}"
        uid = getattr(event, "user_id", None)
        if uid:
            return f"user:{uid}"
        return "global"

    def _remember_context(self, event: AstrMessageEvent, location: Optional[str], intent: str) -> None:
        key = self._session_key(event)
        if not location:
            return
        self._session_memory[key] = {
            "location": location,
            "intent": intent,
            "ts": int(time.time()),
        }
        self._prune_memory()

    def _get_session_location(self, event: AstrMessageEvent) -> Optional[str]:
        item = self._session_memory.get(self._session_key(event))
        if not item:
            return None
        if int(time.time()) - int(item.get("ts", 0)) > 3600:
            return None
        return item.get("location")

    def _prune_memory(self) -> None:
        now = int(time.time())
        stale = [k for k, v in self._session_memory.items() if now - int(v.get("ts", 0)) > 3600]
        for k in stale:
            self._session_memory.pop(k, None)

    def _resolve_location_name(self, data: Dict[str, Any], fallback: Optional[str]) -> Optional[str]:
        location = data.get("location")
        if isinstance(location, dict):
            return location.get("name") or location.get("input") or fallback
        if isinstance(location, str) and location:
            return location
        return fallback

    def _format_now(self, data: Dict[str, Any]) -> str:
        if not data.get("success"):
            return f"天气查询失败: {data.get('error', 'unknown error')}"

        now = data.get("now", {})
        location = data.get("location")
        if isinstance(location, dict):
            location_name = location.get("name") or location.get("input") or "未知地点"
        else:
            location_name = location or "未知地点"

        return (
            f"{location_name} 当前天气\n"
            f"天气: {now.get('text')}\n"
            f"温度: {now.get('temp')}°C 体感: {now.get('feelsLike')}°C\n"
            f"湿度: {now.get('humidity')} 风向: {now.get('windDir')} 风力: {now.get('windScale')}\n"
            f"降水: {now.get('precip')} 能见度: {now.get('vis')} 气压: {now.get('pressure')}\n"
            f"观测时间: {now.get('obsTime')}\n"
            f"来源: {data.get('source')}"
        )

    def _format_forecast(self, data: Dict[str, Any]) -> str:
        if not data.get("success"):
            return f"天气预报查询失败: {data.get('error', 'unknown error')}"

        lines = [f"{data.get('location')} 未来 {data.get('days')} 天天气:"]
        for item in data.get("forecast", []):
            lines.append(
                f"{item.get('date')} {item.get('textDay')} / {item.get('textNight')} "
                f"{item.get('tempMin')}~{item.get('tempMax')}°C"
            )
        lines.append(f"来源: {data.get('source')}")
        return "\n".join(lines)

    def _format_hourly(self, data: Dict[str, Any]) -> str:
        if not data.get("success"):
            return f"逐小时预报查询失败: {data.get('error', 'unknown error')}"

        lines = [f"{data.get('location')} {data.get('hours')} 逐小时预报(展示前8条):"]
        for item in data.get("hourly", [])[:8]:
            lines.append(
                f"{item.get('time')} {item.get('text')} {item.get('temp')}°C "
                f"降水概率:{item.get('pop')}%"
            )
        lines.append(f"来源: {data.get('source')}")
        return "\n".join(lines)

    def _format_rain(self, data: Dict[str, Any]) -> str:
        if not data.get("success"):
            return f"分钟级降水查询失败: {data.get('error', 'unknown error')}"

        precip = data.get("precipitation", {})
        lines = [f"{data.get('location')} 分钟级降水", f"摘要: {precip.get('summary')}"]
        for item in precip.get("minutely", [])[:8]:
            lines.append(f"{item.get('time')} 降水 {item.get('precip')}mm ({item.get('type')})")
        lines.append(f"来源: {data.get('source')}")
        return "\n".join(lines)

    def _format_warning(self, data: Dict[str, Any]) -> str:
        if not data.get("success"):
            return f"预警查询失败: {data.get('error', 'unknown error')}"

        warning = data.get("warning", {})
        alerts = warning.get("alerts", [])
        lines = [f"{data.get('location')} 预警信息:"]
        if not alerts:
            lines.append("当前无有效预警")
        else:
            for item in alerts[:5]:
                lines.append(f"{item.get('title')} | {item.get('pubTime')}")
        attributions = warning.get("attributions", [])
        if attributions:
            names = []
            for item in attributions:
                if isinstance(item, str) and item.strip():
                    names.append(item.strip())
                elif isinstance(item, dict) and item.get("name"):
                    names.append(str(item.get("name")).strip())
            if names:
                lines.append(f"数据归属: {', '.join(names)}")
        lines.append(f"来源: {data.get('source')}")
        return "\n".join(lines)

    def _format_indices(self, data: Dict[str, Any]) -> str:
        if not data.get("success"):
            return f"生活指数查询失败: {data.get('error', 'unknown error')}"

        lines = [f"{data.get('location')} 生活指数(展示前8条):"]
        for item in data.get("indices", [])[:8]:
            lines.append(f"{item.get('date')} {item.get('name')} {item.get('category')} - {item.get('text')}")
        lines.append(f"来源: {data.get('source')}")
        return "\n".join(lines)

    async def terminate(self):
        logger.info("qweather_astrbot plugin terminated")

    def _to_bool(self, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in {"1", "true", "yes", "y", "on"}
        return bool(v)


