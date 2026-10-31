"""Spec-driven fixed-fractional position sizing. See docs/RISK.md §3.

Volume is always rounded DOWN to the volume step. If even the minimum volume risks more than
the target, the trade is taken at the minimum volume only while that risk stays within
``min_lot_risk_cap_pct`` (user choice: 5%); above it, or beyond leverage/margin, it is rejected.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolSpec:
    """Broker symbol specification. Values below are assumptions until read from Vantage MT5."""

    name: str = "XAUUSD"
    contract_size: float = 100.0
    tick_size: float = 0.01
    tick_value: float = 1.0  # USD per tick per 1.0 lot
    volume_min: float = 0.01
    volume_step: float = 0.01
    volume_max: float = 100.0
    commission_per_lot: float = 0.0  # Standard account assumed spread-only
    account_leverage: float = 500.0  # assumption, verify on demo


@dataclass(frozen=True)
class SizeResult:
    volume: float
    risk_money: float  # money lost if the stop is hit, including costs
    reason: str | None = None  # rejection reason when volume == 0

    @property
    def ok(self) -> bool:
        return self.reason is None


def size_position(
    equity: float,
    risk_pct: float,
    entry: float,
    stop: float,
    spec: SymbolSpec,
    est_slippage: float,
    max_effective_leverage: float,
    min_free_margin_pct: float,
    min_lot_risk_cap_pct: float | None = None,
) -> SizeResult:
    distance = abs(entry - stop)
    if distance <= 0:
        return SizeResult(0.0, 0.0, "invalid_stop")
    budget = equity * risk_pct / 100.0
    loss_per_lot = (distance + est_slippage) / spec.tick_size * spec.tick_value
    loss_per_lot += spec.commission_per_lot
    steps = math.floor(budget / loss_per_lot / spec.volume_step + 1e-9)
    volume = round(min(steps * spec.volume_step, spec.volume_max), 8)
    if volume < spec.volume_min:
        cap = equity * (min_lot_risk_cap_pct or 0.0) / 100.0
        if spec.volume_min * loss_per_lot > cap:
            return SizeResult(0.0, 0.0, "min_lot_exceeds_risk")
        volume = spec.volume_min
    notional_per_lot = entry * spec.contract_size
    max_by_leverage = max_effective_leverage * equity / notional_per_lot
    if volume > max_by_leverage:
        volume = round(math.floor(max_by_leverage / spec.volume_step + 1e-9) * spec.volume_step, 8)
        if volume < spec.volume_min:
            return SizeResult(0.0, 0.0, "leverage_cap")
    margin = volume * notional_per_lot / spec.account_leverage
    if equity - margin < equity * min_free_margin_pct / 100.0:
        return SizeResult(0.0, 0.0, "free_margin")
    return SizeResult(volume, volume * loss_per_lot)
