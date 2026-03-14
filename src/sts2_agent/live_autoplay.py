from __future__ import annotations

from dataclasses import dataclass

from sts2_agent.bridge import HttpGameBridge, HttpGameBridgeConfig
from sts2_agent.models import RunSummary
from sts2_agent.orchestrator import AutoplayOrchestrator, OrchestratorConfig
from sts2_agent.policy import ChatCompletionsConfig, ChatCompletionsPolicy


@dataclass(slots=True)
class LiveAutoplayConfig:
    bridge_base_url: str = "http://127.0.0.1:17654"
    llm_base_url: str = "http://127.0.0.1:8080/v1"
    model: str = "default"
    api_key: str | None = None
    trace_dir: str = "traces/live_llm"
    max_steps: int = 32
    policy_timeout_seconds: float = 20.0
    temperature: float = 0.2
    max_tokens: int = 256
    dry_run: bool = False
    scenario: str = "live_http_bridge"


def run_live_autoplay(config: LiveAutoplayConfig) -> RunSummary:
    bridge = HttpGameBridge(
        HttpGameBridgeConfig(
            base_url=config.bridge_base_url,
            timeout_seconds=config.policy_timeout_seconds,
            scenario=config.scenario,
        )
    )
    policy = ChatCompletionsPolicy(
        ChatCompletionsConfig(
            base_url=config.llm_base_url,
            model=config.model,
            api_key=config.api_key,
            timeout_seconds=config.policy_timeout_seconds,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
    )
    orchestrator = AutoplayOrchestrator(
        bridge=bridge,
        policy=policy,
        config=OrchestratorConfig(
            timeout_seconds=config.policy_timeout_seconds,
            max_steps=config.max_steps,
            trace_dir=config.trace_dir,
            dry_run=config.dry_run,
        ),
    )
    return orchestrator.run(scenario=config.scenario)
