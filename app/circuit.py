"""负载求解：给定单个负载电阻时的回路电流与负载提取功率。

    I   = V_oc / (R_i + R_L)
    P_L = I² · R_L

σ=0 ⇒ R_i=∞ ⇒ I=0、P=0，这里显式处理，不依赖 IEEE 浮点的“数/无穷”巧合。
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class LoadSolution:
    """单个负载点的求解结果。"""

    open_circuit_voltage: float  # V
    internal_resistance: float   # Ω（可能为 +inf）
    load_resistance: float       # Ω
    current: float               # A
    power: float                 # W


def solve_load(
    open_circuit_voltage: float,
    internal_resistance: float,
    load_resistance: float,
) -> LoadSolution:
    """计算负载回路的电流与负载功率。

    ``open_circuit_voltage`` 为有限非负实数；``internal_resistance`` 为正实数
    或 ``math.inf``；``load_resistance`` 为非负有限实数（由 validation 层保证）。

    内阻无穷（理想绝缘工质）时电流、功率恒为零；其余情况按欧姆回路求解，
    不区分短路（R_L=0，P=0）与普通负载。
    """
    if math.isinf(internal_resistance):
        return LoadSolution(
            open_circuit_voltage=open_circuit_voltage,
            internal_resistance=math.inf,
            load_resistance=load_resistance,
            current=0.0,
            power=0.0,
        )

    current = open_circuit_voltage / (internal_resistance + load_resistance)
    power = current * current * load_resistance
    return LoadSolution(
        open_circuit_voltage=open_circuit_voltage,
        internal_resistance=internal_resistance,
        load_resistance=load_resistance,
        current=current,
        power=power,
    )
