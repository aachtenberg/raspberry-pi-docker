import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from threading import Thread

import docker
import requests
from pydantic import BaseModel, Field
from prometheus_client import Counter, Gauge, start_http_server

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _log(level: str, msg: str, **fields: Any) -> None:
    log_level = os.getenv("AI_MONITOR_LOG_LEVEL", "info").strip().lower()
    allowed = {"debug": 10, "info": 20, "warn": 30, "error": 40}
    if allowed.get(level, 20) < allowed.get(log_level, 20):
        return

    payload: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "msg": msg,
    }
    if fields:
        payload.update(fields)
    print(json.dumps(payload, ensure_ascii=False))


@dataclass
class PromQuery:
    name: str
    query: str
    description: str


class Action(BaseModel):
    type: str = Field(..., description="e.g. restart_container | alert | none")
    target: Optional[str] = Field(None, description="container name, if applicable")
    reason: Optional[str] = None


class Triage(BaseModel):
    summary: str
    severity: str = Field(..., description="low | medium | high")
    suspected_causes: List[str] = Field(default_factory=list)
    recommended_actions: List[Action] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


# Prometheus metrics
RESTARTS_TOTAL = Counter(
    "ai_monitor_restarts_total",
    "Total container restarts performed by ai-monitor",
    ["container"],
)
TRIAGE_CALLS_TOTAL = Counter(
    "ai_monitor_triage_calls_total",
    "Total LLM triage calls",
    ["backend", "status"],  # backend: claude|ollama, status: success|timeout|error
)
HEALTHY_CONTAINERS = Gauge(
    "ai_monitor_healthy_containers",
    "Number of healthy containers in allowlist",
)
UNHEALTHY_CONTAINERS = Gauge(
    "ai_monitor_unhealthy_containers",
    "Number of unhealthy/exited containers in allowlist",
)
LAST_RUN_TIMESTAMP = Gauge(
    "ai_monitor_last_run_timestamp",
    "Timestamp of last monitor run",
)


class AiMonitor:
    def __init__(self) -> None:
        self.prometheus_url = os.getenv("PROMETHEUS_URL", "http://prometheus:9090").rstrip("/")
        self.ollama_url = os.getenv("OLLAMA_URL", "http://ollama:11434").rstrip("/")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
        self.interval_seconds = _env_int("AI_MONITOR_INTERVAL_SECONDS", 60)
        self.execute = _env_bool("AI_MONITOR_EXECUTE", False)
        self.self_heal_docker_health = _env_bool("AI_MONITOR_SELF_HEAL_DOCKER_HEALTH", True)
        self.max_restarts_per_run = _env_int("AI_MONITOR_MAX_RESTARTS_PER_RUN", 2)
        self.restart_unhealthy = _env_bool("AI_MONITOR_RESTART_UNHEALTHY", True)
        self.restart_exited = _env_bool("AI_MONITOR_RESTART_EXITED", True)
        self.llm_enabled = _env_bool("AI_MONITOR_LLM_ENABLED", True)
        self.prom_timeout_seconds = _env_int("AI_MONITOR_PROM_TIMEOUT_SECONDS", 5)
        self.ollama_timeout_seconds = _env_int("AI_MONITOR_OLLAMA_TIMEOUT_SECONDS", 30)
        self.allowed_containers = {
            c.strip() for c in os.getenv("AI_MONITOR_ALLOWED_CONTAINERS", "").split(",") if c.strip()
        }
        
        # Claude API support
        self.claude_api_key = os.getenv("CLAUDE_API_KEY")
        self.claude_model = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
        self.use_claude = bool(self.claude_api_key and ANTHROPIC_AVAILABLE)
        if self.use_claude:
            self._anthropic_client = Anthropic(api_key=self.claude_api_key)

        self._docker_client = docker.DockerClient(base_url="unix://var/run/docker.sock")
        self._last_restart: Dict[str, float] = {}

    # ----------------------------- Prometheus ---------------------------------
    def prom_query(self, query: str, timeout_seconds: int = 10) -> Dict[str, Any]:
        url = f"{self.prometheus_url}/api/v1/query"
        response = requests.get(url, params={"query": query}, timeout=timeout_seconds)
        response.raise_for_status()
        return response.json()

    def gather_snapshot(self) -> Dict[str, Any]:
        queries = [
            PromQuery(
                name="down_targets",
                query='up == 0',
                description="Any Prometheus scrape targets currently down",
            ),
            PromQuery(
                name="container_mem_top",
                query='topk(5, docker_container_mem_usage)',
                description="Top container memory usage (bytes) if available",
            ),
            PromQuery(
                name="container_cpu_top",
                query='topk(5, rate(container_cpu_usage_seconds_total[5m]))',
                description="Top container CPU usage (cores) if available",
            ),
        ]

        results: Dict[str, Any] = {}
        for q in queries:
            try:
                payload = self.prom_query(q.query, timeout_seconds=self.prom_timeout_seconds)
                series = payload.get("data", {}).get("result", [])
                results[q.name] = {
                    "description": q.description,
                    "query": q.query,
                    "result": series,
                }
            except Exception as e:
                results[q.name] = {
                    "description": q.description,
                    "query": q.query,
                    "error": str(e),
                    "result": [],
                }

        # Docker health snapshot (local ground truth)
        results["docker_health"] = self._docker_health_snapshot()
        return results

    # ------------------------------- Docker -----------------------------------
    def _docker_health_snapshot(self) -> Dict[str, Any]:
        snapshot: Dict[str, Any] = {"containers": []}
        try:
            containers = self._docker_client.containers.list(all=True)
            for c in containers:
                attrs = c.attrs or {}
                state = (attrs.get("State") or {})
                health = (state.get("Health") or {}) if isinstance(state, dict) else {}
                snapshot["containers"].append(
                    {
                        "name": c.name,
                        "status": state.get("Status"),
                        "health": health.get("Status"),
                        "exit_code": state.get("ExitCode"),
                    }
                )
        except Exception as e:
            snapshot["error"] = str(e)
        return snapshot

    def _restart_container(self, container_name: str) -> bool:
        cooldown_seconds = _env_int("AI_MONITOR_RESTART_COOLDOWN_SECONDS", 600)
        now = time.time()
        last = self._last_restart.get(container_name, 0)
        if now - last < cooldown_seconds:
            _log("warn", "Restart skipped (cooldown)", container=container_name, cooldown_seconds=cooldown_seconds)
            return False

        if self.allowed_containers and container_name not in self.allowed_containers:
            _log("warn", "Restart blocked (not allowlisted)", container=container_name)
            return False

        try:
            container = self._docker_client.containers.get(container_name)
            _log("warn", "Restarting container", container=container_name)
            container.restart(timeout=10)
            self._last_restart[container_name] = now
            RESTARTS_TOTAL.labels(container=container_name).inc()
            return True
        except Exception as e:
            _log("error", "Restart failed", container=container_name, error=str(e))
            return False

    def _containers_needing_restart(self, docker_health: List[Dict[str, Any]]) -> List[str]:
        candidates: List[str] = []
        for c in docker_health:
            name = c.get("name")
            if not name:
                continue
            if self.allowed_containers and name not in self.allowed_containers:
                continue
            health = (c.get("health") or "").lower() if isinstance(c.get("health"), str) else ""
            status = (c.get("status") or "").lower() if isinstance(c.get("status"), str) else ""

            if self.restart_unhealthy and health == "unhealthy":
                candidates.append(name)
                continue

            if self.restart_exited and status in {"exited", "dead"}:
                candidates.append(name)

        # Stable ordering for predictable behavior
        return sorted(set(candidates))

    # -------------------------------- Ollama ----------------------------------
    def _ollama_tags(self) -> List[str]:
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=10)
            response.raise_for_status()
            models = response.json().get("models", [])
            return [m.get("name", "") for m in models if m.get("name")]
        except Exception:
            return []

    def _ollama_pull(self, model: str) -> None:
        _log("info", "Pulling Ollama model (first run can take a while)", model=model)
        response = requests.post(
            f"{self.ollama_url}/api/pull",
            json={"name": model, "stream": False},
            timeout=3600,
        )
        response.raise_for_status()

    def ensure_model(self) -> None:
        tags = self._ollama_tags()
        if any(t == self.ollama_model or t.startswith(self.ollama_model + ":") for t in tags):
            return
        self._ollama_pull(self.ollama_model)

    def ask_llm_for_triage(self, snapshot: Dict[str, Any]) -> Optional[Triage]:
        if self.use_claude:
            return self._ask_claude_for_triage(snapshot)
        else:
            return self._ask_ollama_for_triage(snapshot)

    def _ask_claude_for_triage(self, snapshot: Dict[str, Any]) -> Optional[Triage]:
        prompt = (
            "You are an SRE assistant for a Raspberry Pi docker-compose stack. "
            "Given the JSON snapshot, produce a concise triage response. "
            "Return ONLY valid JSON that matches this schema:\n"
            '{"summary": string, "severity": "low"|"medium"|"high", '
            '"suspected_causes": string[], '
            '"recommended_actions": [{"type": "restart_container"|"alert"|"none", "target": string|null, "reason": string|null}], '
            '"confidence": number }\n\n'
            "Constraints:\n"
            "- Be conservative: prefer alert/none over restarts.\n"
            "- If you recommend a restart_container, set target to the exact container name.\n"
            "- If everything looks fine, severity=low and action=none.\n\n"
            f"SNAPSHOT:\n{json.dumps(snapshot, ensure_ascii=False)}"
        )

        try:
            response = self._anthropic_client.messages.create(
                model=self.claude_model,
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            raw = response.content[0].text.strip()
            if not raw:
                return None
            
            # Extract JSON from markdown code blocks if present
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            
            data = json.loads(raw)
            
            # Normalize confidence
            confidence = data.get("confidence")
            if isinstance(confidence, (int, float)):
                if confidence > 1 and confidence <= 100:
                    data["confidence"] = float(confidence) / 100.0
            
            # Normalize suspected_causes
            suspected = data.get("suspected_causes")
            if isinstance(suspected, list):
                normalized: List[str] = []
                for item in suspected:
                    if isinstance(item, str):
                        normalized.append(item)
                    elif isinstance(item, dict):
                        normalized.append(
                            str(item.get("reason") or item.get("cause") or json.dumps(item, ensure_ascii=False))
                        )
                    else:
                        normalized.append(str(item))
                data["suspected_causes"] = normalized
            
            TRIAGE_CALLS_TOTAL.labels(backend="claude", status="success").inc()
            return Triage.model_validate(data)
        except requests.exceptions.Timeout:
            TRIAGE_CALLS_TOTAL.labels(backend="claude", status="timeout").inc()
            _log("error", "Claude triage failed", error="timeout")
            return None
        except Exception as e:
            TRIAGE_CALLS_TOTAL.labels(backend="claude", status="error").inc()
            _log("error", "Claude triage failed", error=str(e))
            return None

    def _ask_ollama_for_triage(self, snapshot: Dict[str, Any]) -> Optional[Triage]:
        prompt = (
            "You are an SRE assistant for a Raspberry Pi docker-compose stack. "
            "Given the JSON snapshot, produce a concise triage response. "
            "Return ONLY valid JSON that matches this schema:\n"
            "{\"summary\": string, \"severity\": \"low\"|\"medium\"|\"high\", "
            "\"suspected_causes\": string[], "
            "\"recommended_actions\": [{\"type\": \"restart_container\"|\"alert\"|\"none\", \"target\": string|null, \"reason\": string|null}], "
            "\"confidence\": number }\n\n"
            "Constraints:\n"
            "- Be conservative: prefer alert/none over restarts.\n"
            "- If you recommend a restart_container, set target to the exact container name.\n"
            "- If everything looks fine, severity=low and action=none.\n\n"
            f"SNAPSHOT:\n{json.dumps(snapshot, ensure_ascii=False)}"
        )

        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
                timeout=self.ollama_timeout_seconds,
            )
            response.raise_for_status()
            raw = response.json().get("response", "").strip()
            if not raw:
                return None
            # Some small local models occasionally return slightly-off JSON.
            # Normalize to our schema instead of failing hard.
            data = json.loads(raw)

            confidence = data.get("confidence")
            if isinstance(confidence, (int, float)):
                if confidence > 1 and confidence <= 100:
                    data["confidence"] = float(confidence) / 100.0

            suspected = data.get("suspected_causes")
            if isinstance(suspected, list):
                normalized: List[str] = []
                for item in suspected:
                    if isinstance(item, str):
                        normalized.append(item)
                    elif isinstance(item, dict):
                        normalized.append(
                            str(item.get("reason") or item.get("cause") or json.dumps(item, ensure_ascii=False))
                        )
                    else:
                        normalized.append(str(item))
                data["suspected_causes"] = normalized

            TRIAGE_CALLS_TOTAL.labels(backend="ollama", status="success").inc()
            return Triage.model_validate(data)
        except requests.exceptions.Timeout:
            TRIAGE_CALLS_TOTAL.labels(backend="ollama", status="timeout").inc()
            _log("error", "Ollama triage failed", error="timeout")
            return None
        except Exception as e:
            TRIAGE_CALLS_TOTAL.labels(backend="ollama", status="error").inc()
            _log("error", "Ollama triage failed", error=str(e))
            return None

    # --------------------------------- Loop -----------------------------------
    def run_once(self) -> None:
        snapshot = self.gather_snapshot()
        LAST_RUN_TIMESTAMP.set(time.time())

        # fast-path: if nothing down and docker health is ok, we can avoid LLM calls
        down_targets = snapshot.get("down_targets", {}).get("result", [])
        docker_health = snapshot.get("docker_health", {}).get("containers", [])
        relevant = (
            [c for c in docker_health if c.get("name") in self.allowed_containers]
            if self.allowed_containers
            else docker_health
        )
        unhealthy = [c for c in relevant if c.get("health") == "unhealthy"]
        exited = [c for c in relevant if (c.get("status") or "").lower() in {"exited", "dead"}]
        
        # Update health gauges
        UNHEALTHY_CONTAINERS.set(len(unhealthy) + len(exited))
        HEALTHY_CONTAINERS.set(len(relevant) - len(unhealthy) - len(exited))

        restarts_this_run = 0
        if self.execute and self.self_heal_docker_health:
            for name in self._containers_needing_restart(docker_health):
                if self.max_restarts_per_run >= 0 and restarts_this_run >= self.max_restarts_per_run:
                    _log(
                        "warn",
                        "Restart cap reached for this run",
                        max_restarts_per_run=self.max_restarts_per_run,
                    )
                    break
                if self._restart_container(name):
                    restarts_this_run += 1

        # If we took remediation actions, don't block the loop on LLM calls.
        # Also avoids triaging on a snapshot taken before restarts.
        if restarts_this_run > 0:
            _log("info", "Self-heal actions executed", restarts=restarts_this_run)
            return

        if not down_targets and not unhealthy:
            if not exited:
                _log("info", "Healthy snapshot", checks="up + docker health")
                return
            _log("warn", "Containers exited", containers=[c.get("name") for c in exited if c.get("name")])
            return

        if not self.llm_enabled:
            return

        triage = self.ask_llm_for_triage(snapshot)
        if not triage:
            _log("warn", "No triage returned")
            return

        _log(
            "info",
            "AI triage",
            severity=triage.severity,
            confidence=triage.confidence,
            summary=triage.summary,
            actions=[a.model_dump() for a in triage.recommended_actions],
        )

        if not self.execute:
            return

        for action in triage.recommended_actions:
            if action.type != "restart_container" or not action.target:
                continue
            self._restart_container(action.target)

    def run_forever(self) -> None:
        # Start Prometheus metrics HTTP server in background
        metrics_port = _env_int("AI_MONITOR_METRICS_PORT", 8000)
        Thread(target=start_http_server, args=(metrics_port,), daemon=True).start()
        _log("info", "Prometheus metrics server started", port=metrics_port)
        
        llm_backend = "claude" if self.use_claude else "ollama"
        llm_config = {
            "backend": llm_backend,
            "model": self.claude_model if self.use_claude else self.ollama_model,
        }
        if not self.use_claude:
            llm_config["ollama_url"] = self.ollama_url
        
        _log(
            "info",
            "AI monitor starting",
            prometheus_url=self.prometheus_url,
            llm=llm_config,
            interval_seconds=self.interval_seconds,
            execute=self.execute,
            allowed_containers=sorted(self.allowed_containers),
        )

        # Try model pull on startup; if ollama isn't ready, loop until it is.
        while True:
            try:
                self.ensure_model()
                break
            except Exception as e:
                _log("warn", "Ollama not ready yet; retrying", error=str(e))
                time.sleep(5)

        while True:
            try:
                self.run_once()
            except Exception as e:
                _log("error", "Run loop error", error=str(e))
            time.sleep(self.interval_seconds)


if __name__ == "__main__":
    AiMonitor().run_forever()
