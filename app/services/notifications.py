"""Notification service — ntfy, Discord webhook, and generic webhook support."""
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE = (
    "🔭 {verdict} for imaging tonight! Score: {score}/100\n"
    "Filter: {filter_recommendation} | Moon: {moon_illumination}% ({moon_phase})\n"
    "Window: {imaging_window} ({imaging_hours}h)\n"
    "Best hour: {best_hour} (score {best_hour_score})\n"
    "Broadband: {broadband_verdict} | Narrowband: {narrowband_verdict}\n"
    "Watch out: {worst_issue}"
)

# Variable definitions for the UI
TEMPLATE_VARIABLES = [
    {"key": "verdict", "label": "Verdict", "example": "GO / MAYBE / NO-GO"},
    {"key": "score", "label": "Score", "example": "78"},
    {"key": "filter_recommendation", "label": "Filter Suggestion", "example": "L-Pro"},
    {"key": "moon_illumination", "label": "Moon Illumination %", "example": "42"},
    {"key": "moon_phase", "label": "Moon Phase", "example": "Waxing Gibbous"},
    {"key": "imaging_hours", "label": "Imaging Hours", "example": "6"},
    {"key": "imaging_window", "label": "Imaging Window", "example": "8:30 PM → 2:00 AM"},
    {"key": "best_hour", "label": "Best Hour", "example": "11:00 PM"},
    {"key": "best_hour_score", "label": "Best Hour Score", "example": "92"},
    {"key": "worst_issue", "label": "Worst Issue", "example": "Clouds (35%)"},
    {"key": "broadband_verdict", "label": "Broadband Verdict", "example": "MAYBE"},
    {"key": "narrowband_verdict", "label": "Narrowband Verdict", "example": "GO"},
]


def render_template(template: str, variables: dict) -> str:
    """Render a message template by substituting {variable} placeholders."""
    if not template:
        template = DEFAULT_TEMPLATE
    result = template
    for key, value in variables.items():
        result = result.replace("{" + key + "}", str(value))
    return result


def build_variables(forecast: dict) -> dict:
    """Extract template variables from a forecast data dict."""
    best = forecast.get("best_hour", {}) or {}
    return {
        "verdict": forecast.get("verdict", "?"),
        "score": forecast.get("score", 0),
        "filter_recommendation": forecast.get("filter_recommendation", "?"),
        "moon_illumination": forecast.get("moon_illumination", 0),
        "moon_phase": forecast.get("moon_phase", "?"),
        "imaging_hours": forecast.get("num_hours", 0),
        "imaging_window": forecast.get("imaging_window", "?"),
        "best_hour": best.get("time", "?") if best else "?",
        "best_hour_score": best.get("score", "?") if best else "?",
        "worst_issue": forecast.get("worst_issue", "All clear"),
        "broadband_verdict": forecast.get("broadband_verdict", "?"),
        "narrowband_verdict": forecast.get("narrowband_verdict", "?"),
    }


def build_test_variables() -> dict:
    """Build sample variables for test notifications."""
    return {
        "verdict": "GO",
        "score": 85,
        "filter_recommendation": "L-Pro",
        "moon_illumination": 12,
        "moon_phase": "Waxing Crescent",
        "imaging_hours": 6,
        "imaging_window": "8:30 PM → 2:00 AM",
        "best_hour": "11:00 PM",
        "best_hour_score": 92,
        "worst_issue": "All clear",
        "broadband_verdict": "GO",
        "narrowband_verdict": "GO",
    }


async def send_discord(url: str, title: str, message: str, verdict: str = "") -> dict:
    """Send a Discord webhook message as a rich embed."""
    if verdict == "GO":
        color = 0x16a34a
    elif verdict == "MAYBE":
        color = 0xca8a04
    elif verdict == "NO-GO":
        color = 0xe53e3e
    else:
        color = 0x2563eb

    payload = {"embeds": [{"title": title, "description": message, "color": color}]}

    # Try httpx first, fall back to urllib for environments where httpx has DNS issues
    try:
        timeout = httpx.Timeout(10.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload,
                                      headers={"Content-Type": "application/json"})
            if resp.status_code < 300:
                logger.info(f"Discord sent: {resp.status_code}")
                return {"ok": True}
            else:
                msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.warning(f"Discord failed: {msg}")
                return {"ok": False, "error": msg}
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        logger.warning(f"httpx Discord failed ({type(e).__name__}), trying urllib fallback")
        # Fallback: synchronous urllib (works when httpx has DNS/proxy issues)
        try:
            import json
            from urllib.request import Request, urlopen
            from urllib.error import URLError, HTTPError
            data = json.dumps(payload).encode('utf-8')
            req = Request(url, data=data, headers={"Content-Type": "application/json"})
            resp = urlopen(req, timeout=10)
            code = resp.getcode()
            if code and code < 300:
                logger.info(f"Discord sent via urllib: {code}")
                return {"ok": True}
            else:
                return {"ok": False, "error": f"HTTP {code}"}
        except HTTPError as he:
            body = he.read().decode('utf-8', errors='replace')[:200]
            return {"ok": False, "error": f"HTTP {he.code}: {body}"}
        except URLError as ue:
            return {"ok": False, "error": f"Connection error: {ue.reason}"}
        except Exception as e2:
            return {"ok": False, "error": f"Fallback failed: {type(e2).__name__}: {e2}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


async def send_webhook(url: str, payload: dict) -> dict:
    """Send a generic webhook POST with JSON payload."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code < 300:
                logger.info(f"Webhook sent to {url}: {resp.status_code}")
                return {"ok": True}
            else:
                msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.warning(f"Webhook failed: {msg}")
                return {"ok": False, "error": msg}
    except httpx.ConnectError:
        return {"ok": False, "error": f"Connection failed — could not reach {url}."}
    except httpx.TimeoutException:
        return {"ok": False, "error": "Request timed out after 10 seconds."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


async def send_ntfy(server: str, topic: str, title: str, message: str,
                     priority: str = "default", tags: Optional[list] = None) -> dict:
    """Send a notification via ntfy."""
    url = f"{server.rstrip('/')}/{topic}"
    headers = {"Title": title, "Priority": priority}
    if tags:
        headers["Tags"] = ",".join(tags)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, content=message, headers=headers)
            if resp.status_code < 300:
                logger.info(f"ntfy sent to {topic}: {resp.status_code}")
                return {"ok": True}
            else:
                msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.warning(f"ntfy failed: {msg}")
                return {"ok": False, "error": msg}
    except httpx.ConnectError:
        return {"ok": False, "error": f"Connection failed — could not reach {url}."}
    except httpx.TimeoutException:
        return {"ok": False, "error": "Request timed out after 10 seconds."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


async def send_notification(settings, title: str, message: str,
                             variables: dict) -> dict:
    """Route a notification to the correct method based on user settings."""
    method = settings.notify_method or "ntfy"
    verdict = variables.get("verdict", "")

    if method == "ntfy":
        if not settings.notify_ntfy_topic:
            return {"ok": False, "error": "ntfy topic not configured."}
        tags = ["telescope", "star"]
        if verdict == "GO":
            tags.append("white_check_mark")
            priority = "high"
        else:
            tags.append("warning")
            priority = "default"
        return await send_ntfy(
            settings.notify_ntfy_server or "https://ntfy.sh",
            settings.notify_ntfy_topic, title, message,
            priority=priority, tags=tags
        )
    elif method == "discord":
        if not settings.notify_discord_url:
            return {"ok": False, "error": "Discord webhook URL not configured."}
        return await send_discord(settings.notify_discord_url, title, message, verdict)
    elif method == "webhook":
        if not settings.notify_webhook_url:
            return {"ok": False, "error": "Webhook URL not configured."}
        payload = {**variables, "title": title, "message": message}
        return await send_webhook(settings.notify_webhook_url, payload)
    else:
        return {"ok": False, "error": f"Unknown notification method: {method}"}


async def send_imaging_alert(settings, forecast: dict):
    """Send an imaging alert based on user's notification settings."""
    if not settings.notify_enabled:
        return

    score = forecast.get("score", 0)
    if score < settings.notify_go_threshold:
        return

    variables = build_variables(forecast)
    template = settings.notify_template or DEFAULT_TEMPLATE
    message = render_template(template, variables)
    title = f"🔭 {variables['verdict']} for Imaging Tonight!"

    result = await send_notification(settings, title, message, variables)
    if not result.get("ok"):
        logger.warning(f"Imaging alert failed: {result.get('error')}")
