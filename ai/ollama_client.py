
"""
Ollama API client wrapper.

Provides a small, swappable interface for generating text
from the local Ollama server.
"""

import json
import time
import threading
import contextvars
from typing import Any, Dict, Generator, List, Optional

import requests

from ai.terminal_ui import terminal


class OllamaClient:
    supports_streaming_observer = True

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "cyn-x:latest",
        timeout: int = 600
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.options = {"num_ctx": 8192, "temperature": 0.7}
        self._configuration_lock = threading.RLock()
        self._request_configuration = contextvars.ContextVar("cynx_ollama_request_configuration", default=None)
        self.timeout = timeout

    def configure(self, model: str, options: Dict[str, Any]) -> None:
        """Swap active model settings together so requests see one configuration."""
        with self._configuration_lock:
            self.model = model
            self.options = dict(options)

    def runtime_configuration(self):
        request_configuration = self._request_configuration.get()
        if request_configuration is not None:
            return request_configuration["model"], dict(request_configuration["options"])
        with self._configuration_lock:
            return self.model, dict(self.options)

    def set_request_configuration(self, model: str, options: Dict[str, Any]):
        return self._request_configuration.set({"model": model, "options": dict(options)})

    def reset_request_configuration(self, token) -> None:
        self._request_configuration.reset(token)

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:

        url = f"{self.base_url}/api/generate"

        model, active_options = self.runtime_configuration()
        generation_options = {**active_options, "num_predict": max_tokens}
        supplied_options = kwargs.pop("options", None)
        if isinstance(supplied_options, dict):
            generation_options.update(supplied_options)
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": stream,
            "options": generation_options,
            **kwargs
        }

        terminal.ollama("CYN-X REQUEST", f"Model={self.model} Streaming={stream}")
        terminal.dim("Prompt tokens may be large...")

        response = requests.post(
            url,
            json=payload,
            stream=stream,
            timeout=self.timeout
        )

        terminal.dim(f"Ollama: {response.status_code}")

        response.raise_for_status()

        # Normal mode
        if not stream:
            return response.json()

        # Streaming mode
        output = ""

        for line in response.iter_lines():
            if not line:
                continue

            try:
                data = json.loads(line.decode("utf-8"))
            except Exception:
                continue

            token = data.get("response", "")

            if token:
                print(
                    token,
                    end="",
                    flush=True
                )
                output += token

            if data.get("done"):
                break

        terminal.result("CYN-X COMPLETE")

        return {
            "response": output,
            "done": True
        }

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Call Ollama's chat endpoint with optional tools.
        """
        on_content = kwargs.pop("on_content", None)

        url = f"{self.base_url}/api/chat"

        # The active saved config supplies defaults; isolated callers may override them.
        model, options = self.runtime_configuration()
        model = kwargs.pop("model", model)
        supplied_options = kwargs.pop("options", None)
        if isinstance(supplied_options, dict):
            options.update(supplied_options)
        for key in ("num_ctx", "temperature", "top_p", "repeat_penalty"):
            if key in kwargs:
                options[key] = kwargs.pop(key)
        num_ctx = options.get("num_ctx", 8192)
        temperature = options.get("temperature", 0.7)

        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "options": options,
            **kwargs
        }

        # Only send tools when tools were actually provided.
        if tools:
            payload["tools"] = tools

        terminal.ollama("OLLAMA CHAT REQUEST", f"Model={model} Messages={len(messages)} Tools={len(tools) if tools else 0} Context={num_ctx} Streaming={stream}")

        # Print a shortened debugging version of the request.
        try:
            debug_payload = {
                "model": self.model,
                "messages": messages,
                "tools": tools
            }

            terminal.json(debug_payload)

        except Exception as exc:
            terminal.error(f"[OLLAMA DEBUG ERROR] {exc}")

        start = time.perf_counter()

        try:
            response = requests.post(
                url,
                json=payload,
                stream=stream,
                timeout=self.timeout
            )

        except requests.RequestException as exc:
            elapsed = time.perf_counter() - start

            terminal.error("OLLAMA CONNECTION ERROR")
            terminal.error(str(exc))
            terminal.timing(f"[OLLAMA DIAG] elapsed_s={elapsed:.2f}")

            raise

        elapsed = time.perf_counter() - start

        terminal.ollama("OLLAMA CHAT STATUS", str(response.status_code))
        terminal.timing(f"[OLLAMA CHAT TIME] {elapsed:.2f}s")

        # Handle server errors with useful diagnostics.
        if response.status_code >= 400:

            try:
                body = response.text
            except Exception:
                body = "<unable to read response body>"

            terminal.error(f"[OLLAMA ERROR STATUS] {response.status_code}")
            terminal.error("[OLLAMA ERROR BODY]")
            terminal.error(body[:8000])

            # Diagnostic information.
            try:
                num_messages = len(messages) if messages else 0
            except Exception:
                num_messages = "unknown"

            try:
                system_prompt_chars = 0

                if messages:
                    for message in messages:
                        if (
                            message.get("role") == "system"
                            and isinstance(
                                message.get("content"),
                                str
                            )
                        ):
                            system_prompt_chars += len(
                                message.get("content")
                            )

            except Exception:
                system_prompt_chars = "unknown"

            try:
                num_tools = len(tools) if tools else 0
            except Exception:
                num_tools = "unknown"

            terminal.timing(
                "[OLLAMA DIAG] "
                f"model={model} "
                f"messages={num_messages} "
                f"system_prompt_chars={system_prompt_chars} "
                f"tools={num_tools} "
                f"elapsed_s={elapsed:.2f}"
            )

            # Handle known peg-native parser errors gracefully.
            is_peg_native_error = (
                isinstance(body, str)
                and (
                    "peg-native" in body
                    or
                    "does not match the expected peg-native" in body
                )
            )

            if is_peg_native_error and tools and not stream:

                terminal.warning(
                    "[OLLAMA CLIENT] Detected peg-native tool parse error; "
                    "retrying this turn without tools so normal generation can continue."
                )

                return self.chat(
                    messages=messages,
                    tools=None,
                    stream=False,
                    model=model,
                    options=options,
                    **kwargs
                )

        # Raise all remaining HTTP errors.
        response.raise_for_status()

        # Normal JSON response.
        if not stream:
            return response.json()

        # Streaming chat response.
        output = ""
        tool_calls = {}
        final_chunk = {}
        output_observed = False

        def notify_first_output():
            nonlocal output_observed
            if not output_observed and on_content is not None:
                output_observed = True
                on_content()

        for line in response.iter_lines():

            if not line:
                continue

            try:
                data = json.loads(
                    line.decode("utf-8")
                )

            except Exception:
                continue

            message = data.get("message", {})

            token = message.get(
                "content",
                ""
            )

            if token:
                terminal.dim(token)
                output += token
                notify_first_output()

            for position, tool_call in enumerate(message.get("tool_calls") or []):
                notify_first_output()
                index = tool_call.get("index", position)
                current = tool_calls.setdefault(index, {})
                current_function = current.setdefault("function", {})
                new_function = tool_call.get("function") or {}

                for key in ("id", "type"):
                    value = tool_call.get(key)
                    if value:
                        previous = current.get(key, "")
                        current[key] = (
                            value
                            if value.startswith(previous)
                            else previous + value
                        )

                for key in ("name", "arguments"):
                    value = new_function.get(key)
                    if value is None:
                        continue
                    previous = current_function.get(key)
                    if isinstance(value, dict) and isinstance(previous, dict):
                        previous.update(value)
                    elif isinstance(value, str) and isinstance(previous, str):
                        current_function[key] = (
                            value
                            if value.startswith(previous)
                            else previous + value
                        )
                    else:
                        current_function[key] = value

            if data.get("done"):
                final_chunk = data
                break

        close = getattr(response, "close", None)
        if callable(close):
            close()

        # A disconnected/aborted stream must not be converted into a
        # successful assistant answer. In particular, never let a partial
        # prefix flow into ChatEngine's conversation history.
        if not final_chunk.get("done"):
            raise RuntimeError(
                "Ollama chat stream ended before its terminal completion chunk."
            )

        if str(final_chunk.get("done_reason") or "").lower() in {
            "length", "max_tokens", "limit"
        }:
            raise RuntimeError(
                "Ollama chat stream ended at its generation limit; response is incomplete."
            )

        if not output.strip() and not tool_calls:
            raise RuntimeError("Ollama chat stream contained no completed answer or tool call.")

        terminal.result("CYN-X CHAT COMPLETE")

        # Ollama sends its token and duration counters on the final `done`
        # chunk. Keep those fields when adapting the streamed response to the
        # dictionary shape consumed by ChatEngine; dropping them made every
        # benchmark token metric appear unavailable.
        telemetry_fields = (
            "model", "created_at", "done_reason", "total_duration",
            "load_duration", "prompt_eval_count", "prompt_eval_duration",
            "eval_count", "eval_duration",
        )
        return {
            "message": {
                "role": "assistant",
                "content": output,
                "tool_calls": list(tool_calls.values())
            },
            "done": bool(final_chunk.get("done")),
            **{key: final_chunk[key] for key in telemetry_fields if key in final_chunk},
        }

    def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 512,
        **kwargs
    ) -> Generator[str, None, None]:

        url = f"{self.base_url}/api/generate"

        model, active_options = self.runtime_configuration()
        generation_options = {**active_options, "num_predict": max_tokens}
        supplied_options = kwargs.pop("options", None)
        if isinstance(supplied_options, dict):
            generation_options.update(supplied_options)
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": generation_options,
            **kwargs
        }

        response = requests.post(
            url,
            json=payload,
            stream=True,
            timeout=self.timeout
        )

        response.raise_for_status()

        for line in response.iter_lines():

            if not line:
                continue

            try:
                data = json.loads(
                    line.decode("utf-8")
                )

            except Exception:
                continue

            token = data.get(
                "response",
                ""
            )

            if token:
                yield token
