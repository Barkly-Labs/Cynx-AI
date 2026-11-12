"""In-memory event history for live web chat request pipelines."""

from datetime import datetime, timezone
import threading
import time


class PipelineEventStore:
    def __init__(self, max_requests=200):
        self._lock = threading.Lock()
        self._requests = {}
        self._max_requests = max_requests

    def create(self, request_id):
        now = time.monotonic()
        with self._lock:
            if request_id in self._requests:
                raise ValueError(f"Pipeline request already exists: {request_id}")

            self._requests[request_id] = {
                "started": now,
                "events": [],
                "done": False,
                "cancel_requested": False,
            }
            self._prune(now)

        self.publish(
            request_id,
            "stage",
            stage="request_received",
            status="completed",
        )

    def publish(self, request_id, event_type, **details):
        with self._lock:
            request = self._requests.get(request_id)
            if request is None or request["done"]:
                return

            self._append_event(request, event_type, details)
            if event_type in {"request_completed", "request_failed"}:
                request["done"] = True
            elif event_type == "request_cancelled":
                request["done"] = True

    def request_cancel(self, request_id):
        with self._lock:
            request = self._requests.get(request_id)
            if request is None or request["done"]:
                return False
            if request["cancel_requested"]:
                return True

            request["cancel_requested"] = True
            self._append_event(request, "cancel_requested", {})
            return True

    def is_cancelled(self, request_id):
        with self._lock:
            request = self._requests.get(request_id)
            return bool(request and request["cancel_requested"])

    def read(self, request_id, after=0):
        with self._lock:
            request = self._requests.get(request_id)
            if request is None:
                return {"events": [], "done": False}

            return {
                "events": [event for event in request["events"] if event["id"] > after],
                "done": request["done"],
            }

    def list_recent(self, limit=40):
        """Return lightweight, sanitized summaries for the developer inspector."""
        with self._lock:
            items = []
            for request_id, request in sorted(
                self._requests.items(),
                key=lambda item: item[1]["started"],
                reverse=True,
            )[: max(1, min(int(limit), 100))]:
                events = request["events"]
                last = events[-1] if events else {}
                stages = [
                    {
                        "stage": event.get("stage"),
                        "status": event.get("status"),
                        "elapsed_seconds": event.get("elapsed_seconds"),
                        "tool_name": event.get("tool_name"),
                    }
                    for event in events
                    if event.get("type") == "stage"
                ]
                items.append(
                    {
                        "request_id": request_id,
                        "done": request["done"],
                        "cancel_requested": request["cancel_requested"],
                        "elapsed_seconds": last.get("elapsed_seconds", 0),
                        "last_event": last.get("type", ""),
                        "stages": stages,
                    }
                )
            return items

    def _prune(self, now):
        completed = [
            (request_id, value["started"])
            for request_id, value in self._requests.items()
            if value["done"]
        ]
        expired = {
            request_id for request_id, started in completed if now - started > 3600
        }
        for request_id in expired:
            del self._requests[request_id]

        excess = len(self._requests) - self._max_requests
        if excess > 0:
            oldest_completed = sorted(completed, key=lambda item: item[1])
            for request_id, _ in oldest_completed[:excess]:
                self._requests.pop(request_id, None)

    @staticmethod
    def _append_event(request, event_type, details):
        request["events"].append(
            {
                "id": len(request["events"]) + 1,
                "type": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round(time.monotonic() - request["started"], 3),
                **details,
            }
        )
