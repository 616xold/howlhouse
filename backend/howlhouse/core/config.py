from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HOWLHOUSE_", env_file=".env", extra="ignore")

    env: str = "dev"
    log_level: str = "INFO"
    log_json: bool = False
    secret_key: str = "dev-change-me"
    cors_origins: str = ""
    allowed_hosts: str = "*"

    # Storage
    database_url: str = "sqlite:///./howlhouse.db"
    data_dir: str = "./data"
    blob_store: str = "local"
    blob_base_dir: str = "./blob"
    s3_endpoint: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str = ""
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_prefix: str = ""

    # LLM providers (optional; used in later milestones)
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # Agent package + sandbox controls
    agent_zip_max_bytes: int = 1_000_000
    agent_extract_max_bytes: int = 4_000_000
    agent_strategy_max_chars: int = 10_000

    sandbox_docker_image: str = "python:3.11.11-slim-bookworm"
    sandbox_allow_local_fallback: bool = False
    enable_unsafe_local_agent_runtime: bool = False
    allow_degraded_start_without_docker: bool = False
    sandbox_act_timeout_ms: int = 750
    sandbox_max_observation_bytes: int = 65_536
    sandbox_max_action_bytes: int = 16_384
    sandbox_max_calls_per_match: int = 1_000
    sandbox_cpu_limit: str = "0.5"
    sandbox_memory_limit: str = "256m"
    sandbox_pids_limit: int = 128

    # Worker queue (M11)
    worker_id: str = ""
    worker_concurrency: int = 1
    worker_poll_interval_ms: int = 500
    worker_lease_seconds: int = 30
    worker_stale_after_seconds: int = 120
    embedded_worker_enabled: bool = True
    worker_metrics_enabled: bool = False
    worker_metrics_port: int = 9100

    # Optional identity adapter (M7)
    identity_enabled: bool = False
    identity_verify_url: str | None = None
    identity_token_header: str = "authorization"
    identity_rate_limit_window_s: int = 60
    identity_rate_limit_max_failures: int = 20
    trust_proxy_headers: bool = False
    trusted_proxy_hops: int = 1
    trusted_proxy_cidrs: str = ""
    identity_verify_host_allowlist: str = ""

    # Access control and quotas (M12)
    auth_mode: str = "open"  # open | verified | admin
    admin_tokens: str = ""
    admin_token_header: str = "X-HowlHouse-Admin"
    quota_match_create_max: int = 0
    quota_match_create_window_s: int = 0
    quota_match_run_max: int = 0
    quota_match_run_window_s: int = 0
    quota_agent_upload_max: int = 0
    quota_agent_upload_window_s: int = 0
    quota_prediction_mutation_max: int = 0
    quota_prediction_mutation_window_s: int = 0
    quota_tournament_create_max: int = 0
    quota_tournament_create_window_s: int = 0
    quota_tournament_run_max: int = 0
    quota_tournament_run_window_s: int = 0
    quota_recap_publish_max: int = 0
    quota_recap_publish_window_s: int = 0

    # Retention / pruning (M13)
    retention_usage_events_days: int = 30
    retention_jobs_days: int = 14
    retention_enabled: bool = True

    # Optional outbound recap distribution (M7)
    distribution_enabled: bool = False
    distribution_post_url: str | None = None
    distribution_post_host_allowlist: str = ""

    # Metrics + tracing (M8)
    metrics_enabled: bool = False
    metrics_path: str = "/metrics"
    tracing_enabled: bool = False
    tracing_service_name: str = "howlhouse"
    tracing_otlp_endpoint: str = ""
    tracing_sample_rate: float = 1.0
    event_bus_history_limit: int = 512


settings = Settings()
