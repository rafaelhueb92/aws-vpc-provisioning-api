import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class Settings:

    aws_region: str =  "us-east-1"
    aws_endpoint_url: Optional[str] = None
    log_level: str = "INFO"
    vpc_waiter_delay: int = 5
    vpc_waiter_max_attempts: int = 12
    vpc_waiter_enabled: bool = True
    subnet_max_workers: int = 5
    subnet_map_public_ip: bool = True
    subnet_waiter_delay: int = 5
    subnet_waiter_max_attempts: int = 12
    vpc_table: Optional[str] = None
    extra: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "Settings":
        return cls(
            aws_region=os.getenv("AWS_REGION",cls.aws_region),
            aws_endpoint_url=os.getenv("AWS_ENDPOINT_URL", cls.aws_endpoint_url),
            log_level=os.getenv("LOG_LEVEL", cls.log_level).upper(),
            vpc_waiter_delay=int(os.getenv("VPC_WAITER_DELAY", cls.vpc_waiter_delay)),
            vpc_waiter_max_attempts=int(
                os.getenv("VPC_WAITER_MAX_ATTEMPTS", cls.vpc_waiter_max_attempts)
            ),
            vpc_waiter_enabled=(
                str(os.getenv("VPC_WAITER_ENABLED", cls.vpc_waiter_enabled)).lower()
                in ("1", "true", "yes", "on")
            ),
            subnet_max_workers=int(os.getenv("SUBNET_MAX_WORKERS", cls.subnet_max_workers)),
            subnet_map_public_ip=(
                str(os.getenv("SUBNET_MAP_PUBLIC_IP", cls.subnet_map_public_ip)).lower()
                in ("1", "true", "yes", "on")
            ),
            subnet_waiter_delay=int(
                os.getenv("SUBNET_WAITER_DELAY", cls.subnet_waiter_delay)
            ),
            subnet_waiter_max_attempts=int(
                os.getenv("SUBNET_WAITER_MAX_ATTEMPTS", cls.subnet_waiter_max_attempts)
            ),
            vpc_table=os.getenv("DDB_TABLE_NAME", cls.vpc_table),
        )

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
