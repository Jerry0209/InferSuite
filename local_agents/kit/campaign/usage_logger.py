"""usage_logger.py — litellm proxy callback: one JSONL row per completed model call.

Purpose (ML_typeid campaign): the .traj banks only CUMULATIVE token usage
(info.model_stats), so time-resolved token attribution needs the proxy to record
each request as it completes. Rows land on the HOST epoch clock — the same clock
as the 10 Hz cpu.stat pollers and the 2 Hz cmdlog — so token events align with
the fence timeline directly, no cross-correlation step.

Wire-up (litellm_glm_typeid.yaml):
    litellm_settings:
      callbacks: usage_logger.proxy_handler_instance
The module resolves via PYTHONPATH (start_proxy exports this dir); the output
path comes from USAGE_LOG (per-episode, set by the typeid runner). Accounting
happens on the proxy's response path — the agent and tools see nothing.
"""
import json, os, time

from litellm.integrations.custom_logger import CustomLogger


class UsageLogger(CustomLogger):
    def _write(self, kwargs, response_obj, start_time, end_time):
        path = os.environ.get("USAGE_LOG")
        if not path:
            return
        usage = getattr(response_obj, "usage", None)
        row = {
            "ts_start": start_time.timestamp(),
            "ts_end": end_time.timestamp(),
            "latency_s": (end_time - start_time).total_seconds(),
            "model": kwargs.get("model"),
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
            "status": "success",
        }
        with open(path, "a") as fh:
            fh.write(json.dumps(row) + "\n")
            fh.flush()

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._write(kwargs, response_obj, start_time, end_time)

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._write(kwargs, response_obj, start_time, end_time)

    def log_failure_event(self, kwargs, response_obj, start_time, end_time):
        path = os.environ.get("USAGE_LOG")
        if not path:
            return
        with open(path, "a") as fh:
            fh.write(json.dumps({"ts_start": start_time.timestamp(),
                                 "ts_end": end_time.timestamp(),
                                 "status": "failure",
                                 "error": str(kwargs.get("exception", ""))[:200]}) + "\n")
            fh.flush()

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        self.log_failure_event(kwargs, response_obj, start_time, end_time)


proxy_handler_instance = UsageLogger()
