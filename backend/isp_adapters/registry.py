from isp_adapters.base import ISPAdapter
from isp_adapters.jenny_internet import JennyInternetAdapter
from isp_adapters.custom import CustomAdapter


class ISPAdapterRegistry:
    _adapters: dict[str, type[ISPAdapter]] = {
        "jenny_internet": JennyInternetAdapter,
        "custom": CustomAdapter,
    }

    _instances: dict[str, ISPAdapter] = {}

    @classmethod
    def register(cls, name: str, adapter_cls: type[ISPAdapter]) -> None:
        cls._adapters[name.lower()] = adapter_cls

    @classmethod
    def create(cls, name: str, **kwargs) -> ISPAdapter | None:
        adapter_cls = cls._adapters.get(name.lower())
        if not adapter_cls:
            return None

        key = f"{name}:{kwargs.get('api_base_url', '')}:{kwargs.get('api_key', '')[:8]}"
        if key not in cls._instances:
            cls._instances[key] = adapter_cls(**kwargs)
        return cls._instances[key]

    @classmethod
    def available_adapters(cls) -> list[str]:
        return list(cls._adapters.keys())
