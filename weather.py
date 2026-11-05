"""Free weather lookup with Open-Meteo (no API key required)."""

import logging

import httpx

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WEATHER_CODES = {
    0: "Clear",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    56: "Freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light showers",
    81: "Showers",
    82: "Heavy showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with hail",
}


async def get_weather(city: str, timezone: str) -> str | None:
    """Return a short line like 'Partly cloudy, 27°C', or None on failure."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            geo_response = await client.get(
                GEOCODING_URL,
                params={
                    "name": city,
                    "count": 1,
                    "language": "en",
                    "format": "json",
                },
            )
            geo_response.raise_for_status()
            results = geo_response.json().get("results") or []
            if not results:
                logger.warning("No weather location found for %s", city)
                return None

            latitude = results[0]["latitude"]
            longitude = results[0]["longitude"]

            forecast_response = await client.get(
                FORECAST_URL,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": "temperature_2m,weather_code",
                    "timezone": timezone,
                },
            )
            forecast_response.raise_for_status()
            current = forecast_response.json().get("current") or {}

            temperature = current.get("temperature_2m")
            code = current.get("weather_code")
            if temperature is None:
                return None

            description = WEATHER_CODES.get(int(code), "Unknown")
            return f"{description}, {round(float(temperature))}°C"
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        logger.warning("Weather lookup failed: %s", exc)
        return None
