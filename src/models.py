"""Typed data objects passed down the pipeline.

Each stage produces/consumes these so it can be built and tested in isolation.
All models support JSON round-tripping (used by the --mock path and tests).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class IndexQuote:
    name: str          # "S&P 500"
    symbol: str        # "^GSPC"
    price: float       # last regular-market price
    change_pct: float  # daily % change, e.g. 0.81 for +0.81%


@dataclass
class Mover:
    symbol: str        # "NVDA"
    name: str          # "NVIDIA Corporation"
    price: float
    change_pct: float


@dataclass
class AssetQuote:
    """A cross-asset quote (crypto, commodity, or macro indicator)."""
    name: str          # "Bitcoin", "Gold", "US 10Y Yield"
    symbol: str        # "BTC-USD", "GC=F", "^TNX"
    value: float       # latest level/price in the asset's native unit
    change_pct: float  # daily % change (relative)
    change_abs: float  # daily change in native units (used for yield bps)
    fmt: str           # "usd_large" | "usd" | "level" | "yield"


@dataclass
class Headline:
    title: str
    url: str


@dataclass
class Narrative:
    summary_text: str = ""
    headlines: list[Headline] = field(default_factory=list)


@dataclass
class MarketSummary:
    date: str                                   # ISO date the data represents, e.g. "2026-05-29"
    indices: list[IndexQuote] = field(default_factory=list)
    crypto: list[AssetQuote] = field(default_factory=list)
    commodities: list[AssetQuote] = field(default_factory=list)
    gainers: list[Mover] = field(default_factory=list)
    losers: list[Mover] = field(default_factory=list)
    narrative: Narrative = field(default_factory=Narrative)

    # --- JSON round-tripping -------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MarketSummary":
        return cls(
            date=data["date"],
            indices=[IndexQuote(**q) for q in data.get("indices", [])],
            crypto=[AssetQuote(**a) for a in data.get("crypto", [])],
            commodities=[AssetQuote(**a) for a in data.get("commodities", [])],
            gainers=[Mover(**m) for m in data.get("gainers", [])],
            losers=[Mover(**m) for m in data.get("losers", [])],
            narrative=Narrative(
                summary_text=data.get("narrative", {}).get("summary_text", ""),
                headlines=[
                    Headline(**h)
                    for h in data.get("narrative", {}).get("headlines", [])
                ],
            ),
        )
