import re
from uuid import UUID

class OrderMiiUUID:
    ORDER_MII_UUID_PREFIX = "8637e025-ae91-48de"

    MARKETS_AND_COUNTRY_CODES = {
        "BE": 32,
        "IT": 39,
        "CH": 41,
        "ES": 34,
        "DE": 49,
        "FR": 33,
        "FI": 358,
        "UK": 44,
        "DK": 45,
        "SE": 46,
        "NL": 31,
        "PL": 48,
        "NO": 47,
        "US": 1
    }

    def __init__(self, market: str, order_id: int):
        # 🔹 Normalize market name to uppercase
        market = market.strip().upper()
        self.country_number = self.map_market_to_country_code(market)
        self.order_id = int(order_id)
        self.market = market  # optional, to keep the normalized name

    @classmethod
    def map_market_to_country_code(cls, market: str) -> int:
        # 🔹 Case-insensitive lookup
        market = market.strip().upper()
        if market not in cls.MARKETS_AND_COUNTRY_CODES:
            raise ValueError(f"Unknown market: {market}")
        return cls.MARKETS_AND_COUNTRY_CODES[market]

    @classmethod
    def map_country_code_to_market(cls, country_code: int) -> str:
        for market, code in cls.MARKETS_AND_COUNTRY_CODES.items():
            if code == country_code:
                return market
        raise ValueError(f"No market found for country code {country_code}")

    def to_uuid_string(self) -> str:
        return f"{self.ORDER_MII_UUID_PREFIX}-{self.country_number:04X}-{self.order_id:012X}"

    def to_uuid(self) -> UUID:
        return UUID(self.to_uuid_string())

    def __str__(self):
        return self.to_uuid_string()

    @classmethod
    def parse_from_uuid(cls, uuid_obj: UUID) -> "OrderMiiUUID":
        return cls.parse_from_uuid_string(str(uuid_obj))

    @classmethod
    def parse_from_uuid_string(cls, uuid_string: str) -> "OrderMiiUUID":
        pattern = re.compile(
            rf"^{cls.ORDER_MII_UUID_PREFIX}-(?P<country_num>[0-9a-fA-F]{{4}})-(?P<order_id>[0-9a-fA-F]{{12}})$"
        )
        match = pattern.match(uuid_string)
        if not match:
            raise ValueError("Invalid UUID format")

        country_number = int(match.group("country_num"), 16)
        order_id = int(match.group("order_id"), 16)
        market = cls.map_country_code_to_market(country_number)
        return cls(market, order_id)
