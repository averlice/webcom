"""Proof-of-work test pushes for WebCom notification services.

WebCom sends a test push whenever a push service is toggled on (from the
settings page) and every time a server (re)connects, so the owner has proof
the notification pipeline actually works end to end.
"""
from __future__ import annotations


SERVICES = ("ntfy", "prowl", "mgnotify", "pushover")


def _on(value) -> bool:
    return value not in (None, False, 0, "0", "")


def _keyed(settings: dict, name: str) -> str:
    return str(settings.get(name) or "").strip()


def send_test_push(settings: dict, title: str, message: str) -> list[str]:
    """Send a test push through every enabled service in ``settings``.

    Returns human-readable per-service results, e.g.
    ``["ntfy: sent", "MG Notify: failed (no MG Notify API key configured)"]``.
    A service is skipped silently when it is disabled; when it is enabled but
    its required key is missing the attempt fails loudly so the owner knows
    the config is incomplete.
    """
    from powercom_core.notifiers import (
        ntfyNotifier,
        sendMGNotifyNotification,
        sendPushoverNotification,
        sendProwlNotification,
    )

    s = dict(settings)
    results: list[str] = []

    if _on(s.get("ntfy")):
        try:
            topic = _keyed(s, "ntfyTopic")
            if not topic:
                raise NameError("no ntfy topic configured")
            ntfyNotifier(
                _keyed(s, "ntfyUrl") or "https://ntfy.sh",
                topic,
                _keyed(s, "ntfyUser") or None,
                _keyed(s, "ntfyPassword") or None,
            ).sendNotification(title, message)
            results.append("ntfy: sent")
        except Exception as exc:
            results.append(f"ntfy: failed ({exc})")

    if _on(s.get("prowl")):
        try:
            key = _keyed(s, "prowlkey")
            if not key:
                raise NameError("no Prowl API key configured")
            sendProwlNotification(key, title, message)
            results.append("Prowl: sent")
        except Exception as exc:
            results.append(f"Prowl: failed ({exc})")

    if _on(s.get("mgnotify")):
        try:
            key = _keyed(s, "mgnotifykey")
            if not key:
                raise NameError("no MG Notify API key configured")
            sendMGNotifyNotification(key, message, title)
            results.append("MG Notify: sent")
        except Exception as exc:
            results.append(f"MG Notify: failed ({exc})")

    if _on(s.get("pushover")):
        try:
            user = _keyed(s, "pushoveruser")
            token = _keyed(s, "pushovertoken")
            if not user:
                raise NameError("no Pushover user key configured")
            if not token:
                raise NameError("no Pushover app token configured")
            sendPushoverNotification(
                user,
                token,
                title,
                message,
                device=_keyed(s, "pushoverdevice") or None,
                sound=_keyed(s, "pushoversound") or None,
                priority=_keyed(s, "pushoverpriority") or None,
                retry=_keyed(s, "pushoverretry") or None,
                expire=_keyed(s, "pushoverexpire") or None,
            )
            results.append("Pushover: sent")
        except Exception as exc:
            results.append(f"Pushover: failed ({exc})")

    return results


def newly_enabled(before: dict, after: dict) -> list[str]:
    """Services that transitioned from disabled to enabled."""
    return [k for k in SERVICES if not _on(before.get(k)) and _on(after.get(k))]