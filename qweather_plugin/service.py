from __future__ import annotations

import asyncio
import base64
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from cryptography.hazmat.primitives import serialization


WEATHER_CODE_TEXT = {
    0: "晴",
    1: "晴间多云",
    2: "阴",
    3: "多云",
    45: "雾",
    48: "霜雾",
    51: "小雨",
    53: "中雨",
    55: "大雨",
    56: "冻毛毛雨",
    57: "冻雨",
    61: "小雨",
    63: "中雨",
    65: "暴雨",
    66: "冻雨",
    67: "冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雨夹雪",
    80: "阵雨",
    81: "雷阵雨",
    82: "暴雨",
    85: "阵雪",
    86: "雨夹雪",
    95: "雷暴",
    96: "冰雹",
    99: "大冰雹",
}

LAT_LON_RE = re.compile(r"^-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?$")


@dataclass
class WeatherConfig:
    api_host: str
    project_id: str
    credentials_id: str
    private_key_path: str
    private_key_pem: str = ""
    default_location: str = "Beijing"
    lang: str = "zh"
    unit: str = "m"
    warning_local_time: bool = False
    timeout_seconds: int = 15
    openmeteo_fallback: bool = True


class WeatherService:
    def __init__(self, cfg: WeatherConfig, base_dir: Path):
        self.cfg = cfg
        self.base_dir = base_dir
        self._jwt_cache: Optional[Dict[str, Any]] = None
        self._jwt_lock = asyncio.Lock()

    async def weather_now(self, location: Optional[str] = None) -> Dict[str, Any]:
        loc = (location or self.cfg.default_location or "").strip()
        if not loc:
            return {"success": False, "error": "Missing location"}

        resolved = await self.resolve_location(loc)
        if not resolved["success"]:
            if self.cfg.openmeteo_fallback:
                return await self._weather_now_openmeteo(loc)
            return {"success": False, "error": f"Location lookup failed: {resolved['error']}"}

        jwt = await self.get_jwt()
        url = f"https://{self.cfg.api_host}/v7/weather/now"
        headers = self._headers(jwt)

        try:
            async with httpx.AsyncClient(timeout=self.cfg.timeout_seconds) as client:
                resp = await client.get(
                    url,
                    params=self._qweather_params(location=resolved["locationId"], include_unit=True),
                    headers=headers,
                )
            data = resp.json()
            if data.get("code") != "200":
                if self.cfg.openmeteo_fallback:
                    return await self._weather_now_openmeteo(loc)
                return {"success": False, "error": f"Weather API error ({data.get('code')})"}

            now = data.get("now", {})
            return {
                "success": True,
                "location": resolved["name"],
                "fxLink": data.get("fxLink"),
                "now": {
                    "temp": now.get("temp"),
                    "feelsLike": now.get("feelsLike"),
                    "text": now.get("text"),
                    "humidity": now.get("humidity"),
                    "windDir": now.get("windDir"),
                    "windScale": now.get("windScale"),
                    "pressure": now.get("pressure"),
                    "vis": now.get("vis"),
                    "cloud": now.get("cloud"),
                    "dew": now.get("dew"),
                    "precip": now.get("precip"),
                    "obsTime": now.get("obsTime"),
                },
                "source": "QWeather Enterprise API",
            }
        except Exception as exc:
            if self.cfg.openmeteo_fallback:
                return await self._weather_now_openmeteo(loc)
            return {"success": False, "error": f"Weather request failed: {exc}"}

    async def weather_forecast(self, location: Optional[str] = None, days: int = 3) -> Dict[str, Any]:
        loc = (location or self.cfg.default_location or "").strip()
        if not loc:
            return {"success": False, "error": "Missing location"}

        d = max(1, min(int(days), 15))
        endpoint = "3d" if d <= 3 else "7d" if d <= 7 else "15d"
        resolved = await self.resolve_location(loc)
        if not resolved["success"]:
            return {"success": False, "error": f"Location resolution failed: {resolved['error']}"}

        jwt = await self.get_jwt()
        url = f"https://{self.cfg.api_host}/v7/weather/{endpoint}"

        try:
            async with httpx.AsyncClient(timeout=self.cfg.timeout_seconds) as client:
                resp = await client.get(
                    url,
                    params=self._qweather_params(location=resolved["locationId"], include_unit=True),
                    headers=self._headers(jwt),
                )
            data = resp.json()
            if data.get("code") != "200":
                return {"success": False, "error": f"Forecast API error ({data.get('code')})"}

            daily = data.get("daily", [])[:d]
            return {
                "success": True,
                "location": resolved["name"],
                "days": d,
                "forecast": [
                    {
                        "date": x.get("fxDate"),
                        "tempMax": x.get("tempMax"),
                        "tempMin": x.get("tempMin"),
                        "textDay": x.get("textDay"),
                        "textNight": x.get("textNight"),
                        "precip": x.get("precip"),
                    }
                    for x in daily
                ],
                "source": "QWeather Enterprise API",
            }
        except Exception as exc:
            return {"success": False, "error": f"Forecast request failed: {exc}"}

    async def weather_hourly(self, location: Optional[str] = None, hours: str = "24h") -> Dict[str, Any]:
        loc = (location or self.cfg.default_location or "").strip()
        if not loc:
            return {"success": False, "error": "Missing location"}

        hours_param = hours if hours in {"24h", "72h", "168h"} else "24h"
        resolved = await self.resolve_location(loc)
        if not resolved["success"]:
            return {"success": False, "error": f"Location lookup failed: {resolved['error']}"}

        jwt = await self.get_jwt()
        url = f"https://{self.cfg.api_host}/v7/weather/{hours_param}"

        try:
            async with httpx.AsyncClient(timeout=self.cfg.timeout_seconds) as client:
                resp = await client.get(
                    url,
                    params=self._qweather_params(location=resolved["locationId"], include_unit=True),
                    headers=self._headers(jwt),
                )
            data = resp.json()
            if data.get("code") != "200":
                return {"success": False, "error": f"Hourly forecast API error ({data.get('code')})"}

            def to_int(v: Any) -> Optional[int]:
                try:
                    return int(v)
                except Exception:
                    return None

            def to_float(v: Any) -> Optional[float]:
                try:
                    return float(v)
                except Exception:
                    return None

            return {
                "success": True,
                "location": resolved["name"],
                "hours": hours_param,
                "hourly": [
                    {
                        "time": item.get("fxTime"),
                        "temp": to_int(item.get("temp")),
                        "text": item.get("text"),
                        "icon": item.get("icon"),
                        "wind360": item.get("wind360"),
                        "windDir": item.get("windDir"),
                        "windScale": item.get("windScale"),
                        "windSpeed": to_int(item.get("windSpeed")),
                        "humidity": to_int(item.get("humidity")),
                        "precip": to_float(item.get("precip")),
                        "pop": to_int(item.get("pop")) or 0,
                        "pressure": to_int(item.get("pressure")),
                        "cloud": to_int(item.get("cloud")) or 0,
                        "dew": to_int(item.get("dew")),
                    }
                    for item in data.get("hourly", [])
                ],
                "source": "QWeather Hourly Forecast API",
            }
        except Exception as exc:
            return {"success": False, "error": f"Hourly forecast request failed: {exc}"}

    async def weather_minutely_precipitation(self, location: Optional[str] = None) -> Dict[str, Any]:
        loc = (location or self.cfg.default_location or "").strip()
        if not loc:
            return {"success": False, "error": "Missing location"}

        resolved = await self.resolve_location(loc)
        if not resolved["success"]:
            return {"success": False, "error": f"Location lookup failed: {resolved['error']}"}

        if not resolved.get("lon") or not resolved.get("lat"):
            return {"success": False, "error": "Unable to extract coordinates for precipitation API"}

        location_param = f"{resolved['lon']},{resolved['lat']}"
        jwt = await self.get_jwt()
        url = f"https://{self.cfg.api_host}/v7/minutely/5m"

        try:
            async with httpx.AsyncClient(timeout=self.cfg.timeout_seconds) as client:
                resp = await client.get(
                    url,
                    params=self._qweather_params(location=location_param, include_unit=True),
                    headers=self._headers(jwt),
                )
            data = resp.json()
            if data.get("code") != "200":
                return {"success": False, "error": f"Precipitation API error ({data.get('code')})"}

            return {
                "success": True,
                "location": resolved["name"],
                "precipitation": {
                    "summary": data.get("summary"),
                    "updateTime": data.get("updateTime"),
                    "fxLink": data.get("fxLink"),
                    "minutely": [
                        {
                            "time": item.get("fxTime"),
                            "precip": float(item.get("precip", 0)),
                            "type": item.get("type"),
                        }
                        for item in data.get("minutely", [])
                    ],
                },
                "source": "QWeather Minutely Precipitation API",
            }
        except Exception as exc:
            return {"success": False, "error": f"Precipitation request failed: {exc}"}

    async def weather_warning(self, location: Optional[str] = None) -> Dict[str, Any]:
        loc = (location or self.cfg.default_location or "").strip()
        if not loc:
            return {"success": False, "error": "Missing location"}

        resolved = await self.resolve_location(loc)
        if not resolved["success"]:
            return {"success": False, "error": f"Location lookup failed: {resolved['error']}"}
        if not resolved.get("lat") or not resolved.get("lon"):
            return {"success": False, "error": "Warning API requires latitude and longitude"}

        jwt = await self.get_jwt()
        url = f"https://{self.cfg.api_host}/weatheralert/v1/current/{resolved['lat']}/{resolved['lon']}"

        try:
            async with httpx.AsyncClient(timeout=self.cfg.timeout_seconds) as client:
                resp = await client.get(
                    url,
                    params={"lang": self.cfg.lang, "localTime": self.cfg.warning_local_time},
                    headers=self._headers(jwt),
                )
            data = resp.json()
            if data.get("code") not in (None, "200"):
                return {"success": False, "error": f"Warning API error ({data.get('code')})"}

            metadata = data.get("metadata") or {}
            attributions = metadata.get("attributions") or []
            raw_alerts = data.get("alerts")
            if raw_alerts is None:
                raw_alerts = data.get("warning", [])
            return {
                "success": True,
                "location": resolved["name"],
                "warning": {
                    "updateTime": data.get("updateTime"),
                    "fxLink": data.get("fxLink"),
                    "attributions": attributions,
                    "alerts": [
                        {
                            "id": alert.get("id"),
                            "sender": alert.get("senderName") or alert.get("sender"),
                            "pubTime": alert.get("issuedTime") or alert.get("pubTime"),
                            "title": alert.get("title")
                            or alert.get("headline")
                            or _pick(alert, "eventType", "name")
                            or alert.get("typeName"),
                            "typeName": _pick(alert, "eventType", "name") or alert.get("typeName"),
                            "type": _pick(alert, "eventType", "code") or alert.get("type"),
                            "level": alert.get("level"),
                            "severity": alert.get("severity"),
                            "severityColor": alert.get("severityColor"),
                            "startTime": alert.get("startTime") or alert.get("effectiveTime"),
                            "endTime": alert.get("endTime") or alert.get("expiresTime"),
                            "status": alert.get("status") or _pick(alert, "messageType", "code"),
                            "description": alert.get("text") or alert.get("description"),
                            "related": alert.get("related"),
                        }
                        for alert in raw_alerts
                    ],
                },
                "source": "QWeather WeatherAlert API",
            }
        except Exception as exc:
            return {"success": False, "error": f"Warning request failed: {exc}"}

    async def weather_indices(self, location: Optional[str] = None, days: str = "1d", index_type: str = "all") -> Dict[str, Any]:
        loc = (location or self.cfg.default_location or "").strip()
        if not loc:
            return {"success": False, "error": "Missing location"}

        resolved = await self.resolve_location(loc)
        if not resolved["success"]:
            return {"success": False, "error": f"Location lookup failed: {resolved['error']}"}

        days_param = days if days in {"1d", "3d"} else "1d"
        params: Dict[str, Any] = self._qweather_params(location=resolved["locationId"], include_unit=False)
        if index_type and index_type != "all":
            params["type"] = index_type

        jwt = await self.get_jwt()
        url = f"https://{self.cfg.api_host}/v7/indices/{days_param}"

        try:
            async with httpx.AsyncClient(timeout=self.cfg.timeout_seconds) as client:
                resp = await client.get(url, params=params, headers=self._headers(jwt))
            data = resp.json()
            if data.get("code") != "200":
                return {"success": False, "error": f"Indices API error ({data.get('code')})"}

            return {
                "success": True,
                "location": resolved["name"],
                "indices": [
                    {
                        "date": item.get("date"),
                        "type": item.get("type"),
                        "name": item.get("name"),
                        "level": item.get("level"),
                        "category": item.get("category"),
                        "text": item.get("text"),
                    }
                    for item in data.get("daily", [])
                ],
                "source": "QWeather Indices API",
            }
        except Exception as exc:
            return {"success": False, "error": f"Indices request failed: {exc}"}

    async def resolve_location(self, location: str) -> Dict[str, Any]:
        input_loc = (location or "").strip()
        if not input_loc:
            return {"success": False, "error": "Missing location"}

        if LAT_LON_RE.match(input_loc):
            lon, lat = [x.strip() for x in input_loc.split(",", 1)]
            return {
                "success": True,
                "locationId": f"{lon},{lat}",
                "name": input_loc,
                "lon": lon,
                "lat": lat,
                "resolvedFrom": "latlon",
            }

        jwt = await self.get_jwt()
        url = f"https://{self.cfg.api_host}/geo/v2/city/lookup"

        try:
            async with httpx.AsyncClient(timeout=self.cfg.timeout_seconds) as client:
                resp = await client.get(
                    url,
                    params={"location": input_loc, "number": 1, "lang": self.cfg.lang},
                    headers=self._headers(jwt),
                )
            data = resp.json()
            locations = data.get("location") or []
            if data.get("code") != "200" or not locations:
                if input_loc.isdigit():
                    return {
                        "success": True,
                        "locationId": input_loc,
                        "name": input_loc,
                        "resolvedFrom": "id",
                    }
                return {"success": False, "error": f"Geo lookup failed ({data.get('code')})"}

            best = locations[0]
            return {
                "success": True,
                "locationId": best.get("id"),
                "name": f"{best.get('name', '')}·{best.get('adm1', '')}".rstrip("·"),
                "lon": best.get("lon"),
                "lat": best.get("lat"),
                "resolvedFrom": "name",
                "raw": best,
            }
        except Exception as exc:
            if input_loc.isdigit():
                return {
                    "success": True,
                    "locationId": input_loc,
                    "name": input_loc,
                    "resolvedFrom": "id",
                }
            return {"success": False, "error": str(exc)}

    async def get_jwt(self) -> str:
        async with self._jwt_lock:
            if self._jwt_cache and time.time() < self._jwt_cache["exp"] - 60:
                return self._jwt_cache["token"]

            token, exp = self._generate_jwt()
            self._jwt_cache = {"token": token, "exp": exp}
            return token

    def _generate_jwt(self) -> tuple[str, int]:
        now = int(time.time())
        payload = {"sub": self.cfg.project_id, "iat": now - 30, "exp": now - 30 + 900}
        header = {"alg": "EdDSA", "kid": self.cfg.credentials_id, "typ": "JWT"}

        encoded_header = _base64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        encoded_payload = _base64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")

        private_key = self._load_private_key()
        signature = private_key.sign(signing_input)
        token = f"{encoded_header}.{encoded_payload}.{_base64url(signature)}"
        return token, payload["exp"]

    def _load_private_key(self):
        pem_text = (self.cfg.private_key_pem or "").strip()
        if pem_text:
            return serialization.load_pem_private_key(pem_text.encode("utf-8"), password=None)

        key_path = (self.cfg.private_key_path or "").strip()
        if not key_path:
            raise ValueError("Missing private key config: set private_key_pem or private_key_path")

        path = Path(key_path)
        if not path.is_absolute():
            path = self.base_dir / path
        if not path.exists():
            raise FileNotFoundError(f"Private key file not found: {path}")

        key_data = path.read_bytes()
        return serialization.load_pem_private_key(key_data, password=None)

    def _headers(self, jwt: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {jwt}",
            "Accept": "application/json",
            "User-Agent": "AstrBot-QWeather/1.0",
        }

    def _qweather_params(self, *, location: str, include_unit: bool) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "location": location,
            "lang": self.cfg.lang,
        }
        if include_unit:
            params["unit"] = self.cfg.unit
        return params

    async def _weather_now_openmeteo(self, location: str) -> Dict[str, Any]:
        input_loc = (location or self.cfg.default_location or "Beijing").strip()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                geo_resp = await client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": input_loc, "count": 1},
                )
                geo_data = geo_resp.json()
                results = geo_data.get("results") or []
                if not results:
                    return {"success": False, "error": f"Location not found: {input_loc}"}

                best = results[0]
                weather_resp = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": best.get("latitude"),
                        "longitude": best.get("longitude"),
                        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,rain,weather_code,wind_speed_10m,wind_direction_10m",
                    },
                )
                weather_data = weather_resp.json()

            current = weather_data.get("current") or {}
            weather_code = current.get("weather_code")
            text = WEATHER_CODE_TEXT.get(weather_code, f"天气代码{weather_code}")

            return {
                "success": True,
                "location": {
                    "input": input_loc,
                    "name": best.get("name"),
                    "latitude": best.get("latitude"),
                    "longitude": best.get("longitude"),
                },
                "now": {
                    "obsTime": current.get("time"),
                    "temp": current.get("temperature_2m"),
                    "feelsLike": current.get("apparent_temperature"),
                    "text": text,
                    "humidity": current.get("relative_humidity_2m"),
                    "windDir": current.get("wind_direction_10m"),
                    "windScale": _wind_to_scale(current.get("wind_speed_10m")),
                    "windSpeed": current.get("wind_speed_10m"),
                    "precip": current.get("rain") or 0,
                },
                "source": "Open-Meteo (free tier)",
            }
        except Exception as exc:
            return {"success": False, "error": f"Open-Meteo API error: {exc}"}


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _wind_to_scale(speed_kmh: Optional[float]) -> Optional[int]:
    if speed_kmh is None:
        return None
    try:
        return round(float(speed_kmh) / 3.38)
    except Exception:
        return None


def _pick(d: Dict[str, Any], *keys: str) -> Any:
    cur: Any = d
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur

