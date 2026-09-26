"""负载区间扫描：生成功率曲线并定位峰值。

经典最大功率传输定理：P_L(R_L)=V_oc²·R_L/(R_i+R_L)² 在 R_L=R_i 处取得
最大值 P_max=V_oc²/(4R_i)。扫描只如实报告采样网格上取到的最高值；理论
最佳负载（=内阻）单独给出，方便核对网格是否覆盖峰值。

扫描逐点复用 ``circuit.solve_load``，与单点核算共用同一套公式，二者在
同一负载处的结果天然一致。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .circuit import solve_load


@dataclass(frozen=True)
class ScanPoint:
    load_resistance: float  # Ω
    current: float          # A
    power: float            # W


@dataclass(frozen=True)
class PowerCurve:
    open_circuit_voltage: float
    internal_resistance: float       # 可能为 +inf（σ=0）
    r_min: float
    r_max: float
    num_points: int
    points: tuple[ScanPoint, ...]

    @property
    def optimal_load(self) -> float | None:
        """理论最佳负载 = 内阻；内阻无穷时为 None。"""
        if math.isinf(self.internal_resistance):
            return None
        return self.internal_resistance

    @property
    def peak(self) -> ScanPoint:
        """采样网格上功率最高的点（并列时取最靠左的采样点）。"""
        return max(self.points, key=lambda point: point.power)


def linspace(r_min: float, r_max: float, num_points: int) -> tuple[float, ...]:
    """闭区间 [r_min, r_max] 上的等间距网格，两端点都包含。"""
    step = (r_max - r_min) / (num_points - 1)
    return tuple(r_min + step * index for index in range(num_points))


def scan_loads(
    open_circuit_voltage: float,
    internal_resistance: float,
    r_min: float,
    r_max: float,
    num_points: int,
) -> PowerCurve:
    """对负载区间做扫描。

    入参合法性（区间次序、点数、负载非负）由 validation 层在调用前保证。
    """
    loads = linspace(r_min, r_max, num_points)
    points_list: list[ScanPoint] = []
    for load in loads:
        solution = solve_load(open_circuit_voltage, internal_resistance, load)
        points_list.append(
            ScanPoint(
                load_resistance=load,
                current=solution.current,
                power=solution.power,
            )
        )
    points = tuple(points_list)
    return PowerCurve(
        open_circuit_voltage=open_circuit_voltage,
        internal_resistance=internal_resistance,
        r_min=r_min,
        r_max=r_max,
        num_points=num_points,
        points=points,
    )
