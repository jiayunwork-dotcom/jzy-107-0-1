# Faraday 式磁流体（MHD）通道电学性能核算服务

常驻 HTTP 服务（Python 3.12 + Flask，标准库做科学计算），只负责法拉第式 MHD
通道本身的感应与负载匹配：

- 开路感应电动势（开路电压）
- 给定负载电阻下的回路电流与负载提取功率
- 对一段负载电阻区间做扫描，给出功率曲线并定位峰值点
- 通道档（几何/工质参数的命名配置）在进程内存取

不含页面，不管电站并网调度或值班台账。

## 物理模型

法拉第式体感应电动势（不是霍尔电压，不涉及载流子迁移率）：

\[
V_{oc}=B\,d\,v
\]

- \(B\)：磁感应强度（T）
- \(d\)：电极间距（m）
- \(v\)：流体横穿通道的速度（m/s）

通道内阻：

\[
R_i=\frac{d}{\sigma A}
\]

- \(\sigma\)：流体电导率（S/m），\(\sigma\to 0\) 时 \(R_i\to\infty\)
- \(A\)：通道截面积（m²）

接负载 \(R_L\) 后：

\[
I=\frac{V_{oc}}{R_i+R_L},\qquad P_L=I^2R_L
\]

经典最大功率传输在 \(R_L=R_i\) 处取得，峰值功率 \(P_{\max}=V_{oc}^2/(4R_i)\)。
\(\sigma=0\)（内阻无穷）时电流与功率恒为零。

## 文件结构（按职责拆分）

| 文件 | 职责 |
| --- | --- |
| `app/induction.py` | 开路电压 \(Bdv\) 与内阻 \(d/(\sigma A)\) 的感应计算 |
| `app/circuit.py` | 给定单个负载时的电流与功率求解 |
| `app/scan.py` | 负载区间扫描、功率曲线与峰值定位 |
| `app/profiles.py` | 通道档的进程内存取（线程安全，不跨重启保留） |
| `app/validation.py` | `ChannelParams` 数据结构与全部输入合法性拦截 |
| `app/api.py` | 薄 HTTP 层：请求收发与调度，不含计算内核 |
| `app/__init__.py` | Flask 应用工厂 |
| `tests/` | 自动化测试（pytest），锁定全部物理判据 |

## 一条命令构建并启动

需要 Docker（带 Compose 插件）：

```bash
docker compose up --build
```

或只用 Docker：

```bash
docker build -t mhd-channel .
docker run --rm -p 8000:8000 mhd-channel
```

服务监听 `0.0.0.0:8000`，只走 HTTP JSON。

## HTTP 接口

通道参数字段（内联给出，或用 `profile` 引用已保存的通道档，二选一）：

| 字段 | 含义 | 单位 | 约束 |
| --- | --- | --- | --- |
| `magnetic_field` | 磁感应强度 \(B\) | T | ≥ 0 |
| `electrode_spacing` | 电极间距 \(d\) | m | > 0 |
| `fluid_velocity` | 流体速度 \(v\) | m/s | ≥ 0 |
| `conductivity` | 电导率 \(\sigma\) | S/m | ≥ 0（允许 0） |
| `cross_section` | 通道截面积 \(A\) | m² | > 0 |

### 1. 单点核算 `POST /compute`

请求体额外带 `load_resistance`（Ω，≥ 0）。

```bash
curl -s http://localhost:8000/compute \
  -H 'Content-Type: application/json' \
  -d '{"magnetic_field":2.0,"electrode_spacing":0.5,
       "fluid_velocity":100.0,"conductivity":10.0,
       "cross_section":0.1,"load_resistance":0.5}'
```

```json
{
  "channel": {
    "magnetic_field": 2.0, "electrode_spacing": 0.5,
    "fluid_velocity": 100.0, "conductivity": 10.0, "cross_section": 0.1
  },
  "profile": null,
  "open_circuit_voltage": 100.0,
  "internal_resistance": 0.5,
  "load_resistance": 0.5,
  "current": 100.0,
  "power": 5000.0
}
```

`internal_resistance` 在电导率为 0 时返回 `null`（表示无穷大），此时
`current`、`power` 均为 0。

### 2. 负载扫描 `POST /scan`

请求体额外带：

- `r_min`：负载区间下限（Ω，≥ 0）
- `r_max`：负载区间上限（Ω，必须 > `r_min`）
- `num_points`：等间距采样点数（整数，2 ~ 10001，含两端点）

```bash
curl -s http://localhost:8000/scan \
  -H 'Content-Type: application/json' \
  -d '{"profile":"benchmark_faraday_2t",
       "r_min":0.0,"r_max":1.0,"num_points":5}'
```

响应给出逐点曲线 `points`、理论最佳负载 `optimal_load`（即内阻；电导率为 0
时为 `null`），以及曲线实际采样到的 `peak`（索引、负载、功率）：

```json
{
  "channel": {"..." : "..."},
  "profile": "benchmark_faraday_2t",
  "open_circuit_voltage": 100.0,
  "internal_resistance": 0.5,
  "r_min": 0.0, "r_max": 1.0, "num_points": 5,
  "optimal_load": 0.5,
  "peak": {"index": 2, "load_resistance": 0.5, "power": 5000.0},
  "points": [ {"load_resistance": 0.0, "current": 200.0, "power": 0.0}, "..." ]
}
```

扫描与单点核算共用同一个求解内核，同一负载处两者结果必然一致。

### 3. 通道档

预置档 `benchmark_faraday_2t`（2 T、100 m/s，开路电压 100 V，内阻 0.5 Ω），
进程启动即可用：

- `GET /profiles`：列出全部通道档
- `GET /profiles/<name>`：取单个通道档
- `PUT /profiles/<name>`：保存/覆盖（请求体为五个通道字段）
- `DELETE /profiles/<name>`：删除

```bash
curl -s -X PUT http://localhost:8000/profiles/lab-rig-1 \
  -H 'Content-Type: application/json' \
  -d '{"magnetic_field":1.5,"electrode_spacing":0.4,
       "fluid_velocity":80.0,"conductivity":8.0,"cross_section":0.08}'
```

通道档仅存进程内，重启不保留。两套通道档分别扫描时曲线互不串用。

### 错误响应

非法输入在进入任何计算前被拦截，HTTP 400：

```json
{"error": "输入不合法", "reasons": ["磁感应强度 B 不能为负", "..."]}
```

通道档不存在返回 HTTP 404，同样带原因。

被拦截的情形包括：磁感应强度为负、电极间距不为正、流体速度为负、电导率为负、
通道截面积不为正；负载为负或缺失；扫描区间端点次序颠倒、采样点数少于 2 等。

## 本地测试

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
```

锁定的正确性判据（每条都能独立构造输入验证）：

1. 磁感应强度翻倍 ⇒ 开路电压翻倍（`tests/test_induction.py`）
2. 流体速度翻倍 ⇒ 开路电压翻倍（`tests/test_induction.py`）
3. 扫描功率曲线峰值落在负载等于内阻处；2 倍内阻处功率下降
   （`tests/test_scan.py`）
4. 电导率为 0 ⇒ 电流、功率均为 0（`tests/test_circuit.py`、`test_scan.py`）
5. 单点核算功率与扫描曲线同负载处一致（`tests/test_scan.py`，HTTP 层在
   `tests/test_api.py` 再锁一次）
6. 2 T、100 m/s 基准档开路电压为 100 V（百伏量级手算基准，回归测试）
