"""Dispatcher configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All settings are read from environment variables."""

    database_uri: str = "postgresql://langgraph:langgraph@langgraph-postgres:5432/langgraph"
    redis_uri: str = "redis://:langgraph@langgraph-redis:6379/0"
    dispatcher_port: int = 8070
    agent_default_image: str = "agflow-claude-code:latest"
    agent_mem_limit: str = "2g"
    agent_cpu_quota: int = 100000
    ag_flow_root: str = "/root/ag.flow"
    langgraph_api_url: str = "http://langgraph-api:8000"
    hitl_question_timeout: int = 1800  # 30 minutes
    task_max_retries: int = 1
    db_pool_min: int = 2
    db_pool_max: int = 10

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
