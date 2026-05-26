from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class KillSwitchStatus:
    triggered: bool
    reason: str = ""
    vix: Optional[float] = None
    us10y_change_bp: Optional[float] = None
    dxy_above_bollinger: Optional[bool] = None


@dataclass
class EarningsData:
    symbol: str
    report_date: datetime
    actual_eps: Optional[float]
    estimated_eps: Optional[float]
    actual_revenue: Optional[float]
    estimated_revenue: Optional[float]
    guidance_direction: Optional[str]  # "up" | "maintain" | "down" | None


@dataclass
class InsiderTrade:
    symbol: str
    filing_date: datetime
    transaction_type: str  # 'P'=공개매수, 'A'=옵션행사, 'G'=증여 등
    shares: float
    value: float
    officer_title: str


@dataclass
class AlertSignal:
    signal_type: str  # "TYPE1" | "TYPE2"
    symbol: str
    company_name: str
    sector: str
    market_cap: float
    conditions_met: dict[str, bool]
    current_price: float
    stop_loss_price: float
    exit_date: Optional[datetime]
    kill_switch_status: KillSwitchStatus
    report_url: Optional[str] = None
    extra: dict = field(default_factory=dict)
