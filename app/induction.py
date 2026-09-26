"""感应计算：法拉第体感应电动势与通道内阻。

公式（长度量纲与 README 一致）：

    V_oc = B * d * v          开路电压（V）
    R_i  = d / (σ * A)        通道内阻（Ω）

这是法拉第式通道的体感应电动势，不是霍尔效应那套载流子迁移率乘磁场
的公式；短路电流也不是开路电压。
"""

from __future__ import annotations

import math

from .validation import ChannelParams


def open_circuit_voltage(
    magnetic_field: float,
    electrode_spacing: float,
    fluid_velocity: float,
) -> float:
    """计算开路感应电压 V_oc = B·d·v（伏特）。

    入参由调用方（validation 层）保证非负且为有限数。
    """
    return magnetic_field * electrode_spacing * fluid_velocity


def internal_resistance(
    electrode_spacing: float,
    conductivity: float,
    cross_section: float,
) -> float:
    """计算通道内阻 R_i = d / (σ·A)（欧姆）。

    电导率 σ 为 0 时内阻为正无穷（``math.inf``），由序列化层转成 JSON null。
    """
    if conductivity == 0.0:
        return math.inf
    return electrode_spacing / (conductivity * cross_section)


def channel_electrics(channel: ChannelParams) -> tuple[float, float]:
    """一次算出某通道的 (开路电压, 内阻)。"""
    v_oc = open_circuit_voltage(
        channel.magnetic_field,
        channel.electrode_spacing,
        channel.fluid_velocity,
    )
    r_i = internal_resistance(
        channel.electrode_spacing,
        channel.conductivity,
        channel.cross_section,
    )
    return v_oc, r_i
