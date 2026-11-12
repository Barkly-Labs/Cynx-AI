
"""
Ollama API client wrapper.

Provides a small, swappable interface for generating text
from the local Ollama server.
"""

import json
import time
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
        self.timeout = timeout

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:

        url = f"{self.base_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
            "options": {
                "num_predict": max_tokens,
                "num_ctx": 8192,
                "temperature": 0.7
            },
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

        # Allow callers to override context size and temperature.
        num_ctx = kwargs.pop("num_ctx", 8192)
        temperature = kwargs.pop("temperature", 0.7)

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {
                "num_ctx": num_ctx,
                "temperature": temperature
            },
            **kwargs
        }

        # Only send tools when tools were actually provided.
        if tools:
            payload["tools"] = tools

        terminal.ollama("OLLAMA CHAT REQUEST", f"Model={self.model} Messages={len(messages)} Tools={len(tools) if tools else 0} Context={num_ctx} Streaming={stream}")

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
                f"model={self.model} "
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
                    num_ctx=num_ctx,
                    temperature=temperature,
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
            "done": True,
            **{key: final_chunk[key] for key in telemetry_fields if key in final_chunk},
        }

    def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 512,
        **kwargs
    ) -> Generator[str, None, None]:

        url = f"{self.base_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "num_predict": max_tokens
            },
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
