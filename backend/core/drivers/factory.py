from core.drivers.base import RouterDriver, RouterConnection, RouterCapabilities
from core.drivers.mikrotik import MikroTikDriver
from core.drivers.tplink import TPLinkDriver
from core.drivers.ubiquiti import UbiquitiDriver
from core.drivers.generic import GenericDriver


class DriverFactory:
    _drivers = {
        "mikrotik": MikroTikDriver,
        "tplink": TPLinkDriver,
        "ubiquiti": UbiquitiDriver,
        "generic": GenericDriver,
        "unknown": GenericDriver,
    }

    @classmethod
    def create(cls, brand: str, connection: RouterConnection) -> RouterDriver:
        driver_cls = cls._drivers.get(brand.lower(), GenericDriver)
        return driver_cls(connection)

    @classmethod
    def register(cls, brand: str, driver_cls: type[RouterDriver]) -> None:
        cls._drivers[brand.lower()] = driver_cls

    @classmethod
    def available_brands(cls) -> list[str]:
        return list(cls._drivers.keys())
