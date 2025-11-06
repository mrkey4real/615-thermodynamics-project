# 1 GW AI数据中心冷却系统热力学建模项目

## 项目概述

基于MEEN 615项目要求，为1 GW AI数据中心设计系统级冷却架构的热力学模型。

### 核心要求
- **总IT负荷**: 1 GW (1,000,000 kW)
- **液冷GPU负荷**: 90% (900 MW) - NVIDIA B200
- **风冷设备负荷**: 10% (100 MW)
- **温度约束**:
  - GPU冷却水最高温度: 40°C
  - 建筑空气最高温度: 25°C

### 项目目标
1. 建立系统级热力学模型（基于能量平衡）
2. 计算PUE和WUE指标
3. 评估社会影响
4. 提出优化方案

---

## 系统架构设计

### 模块化设计原则

采用**简洁的三模块架构**，每个模块独立但通过明确的接口相互作用：

```
┌─────────────────────────────────────────────────┐
│           Datacenter System (主系统)             │
│                                                 │
│  ┌──────────────┐  ┌──────────────┐           │
│  │  GPU Load    │  │ Building Load│           │
│  │   Module     │  │    Module    │           │
│  └──────┬───────┘  └──────┬───────┘           │
│         │                  │                   │
│         └────────┬─────────┘                   │
│                  ▼                              │
│         ┌─────────────────┐                    │
│         │  HVAC System    │                    │
│         │  (Chiller +     │                    │
│         │  Cooling Tower) │                    │
│         └─────────────────┘                    │
└─────────────────────────────────────────────────┘
```

---

## 详细模块规格

### 模块1: GPU负荷模块 (gpu_load.py)

**职责**: 模拟液冷GPU集群的热负荷和冷却需求

#### 输入参数
| 参数 | 符号 | 单位 | 默认值 | 说明 |
|------|------|------|--------|------|
| GPU型号 | - | - | NVIDIA B200 | GPU型号 |
| 单GPU功耗 | P_gpu | kW | 1.2 | 单个GPU的TDP |
| 总热负荷 | Q_total | MW | 900 | 液冷部分总负荷 |
| 利用率 | utilization | % | 100 | GPU使用率（可变） |
| 入口水温 | T_in | °C | 15 | 来自热交换器的冷却水温度 |
| 冷却水流量 | ṁ_water | kg/s | 计算得出 | 循环水流量 |

#### 输出结果
| 参数 | 符号 | 单位 | 说明 |
|------|------|------|------|
| 实际热负荷 | Q_actual | MW | Q_total × utilization |
| 出口水温 | T_out | °C | 基于能量平衡计算 |
| GPU数量 | N_gpu | 个 | Q_total / P_gpu |
| 温度检查 | check | bool | T_out ≤ 40°C |

#### 能量平衡方程
```
Q_actual = ṁ_water × c_p × (T_out - T_in)

其中：
- c_p = 4.186 kJ/(kg·K) - 水的比热容
- T_out = T_in + Q_actual / (ṁ_water × c_p)
```

#### 类结构
```python
class GPULoad:
    def __init__(self, gpu_model, tdp_per_gpu, total_load_mw):
        """初始化GPU负荷模块"""

    def calculate_heat_load(self, utilization):
        """计算实际热负荷"""

    def calculate_outlet_temp(self, T_in, m_dot_water):
        """计算出口水温"""

    def check_constraints(self, T_out):
        """检查温度约束"""
```

---

### 模块2: Building负荷模块 (building_load.py)

**职责**: 模拟建筑内风冷设备的热负荷

#### 输入参数
| 参数 | 符号 | 单位 | 默认值 | 说明 |
|------|------|------|--------|------|
| 风冷设备功率 | Q_aircool | MW | 100 | 10%总负荷 |
| 利用率 | utilization | % | 100 | 设备使用率 |
| 入口空气温度 | T_air_in | °C | 20 | 送风温度 |
| 空气流量 | ṁ_air | kg/s | 计算得出 | 循环风量 |

#### 输出结果
| 参数 | 符号 | 单位 | 说明 |
|------|------|------|------|
| 实际热负荷 | Q_actual | MW | Q_aircool × utilization |
| 出口空气温度 | T_air_out | °C | 基于能量平衡 |
| 温度检查 | check | bool | T_air_out ≤ 25°C |

#### 能量平衡方程
```
Q_actual = ṁ_air × c_p_air × (T_air_out - T_air_in)

其中：
- c_p_air = 1.005 kJ/(kg·K) - 空气比热容
- T_air_out = T_air_in + Q_actual / (ṁ_air × c_p_air)
```

#### 类结构
```python
class BuildingLoad:
    def __init__(self, aircool_load_mw):
        """初始化建筑负荷模块"""

    def calculate_heat_load(self, utilization):
        """计算实际热负荷"""

    def calculate_outlet_temp(self, T_air_in, m_dot_air):
        """计算出口空气温度"""

    def check_constraints(self, T_air_out):
        """检查温度约束"""
```

---

### 模块3: HVAC系统模块 (hvac_system.py)

**职责**: 模拟制冷机组和冷却塔的性能

#### 3.1 Chiller类（制冷机组）

##### 输入参数
| 参数 | 符号 | 单位 | 说明 |
|------|------|------|------|
| 蒸发器热负荷 | Q_evap | MW | 来自GPU和Building的总热负荷 |
| 冷冻水供水温度 | T_chw_supply | °C | 10 | 冷水机出水温度 |
| 冷冻水回水温度 | T_chw_return | °C | 计算 | 来自热交换器 |
| 冷却水入口温度 | T_cw_in | °C | 计算 | 来自冷却塔 |
| 冷却水出口温度 | T_cw_out | °C | 计算 | 到冷却塔 |
| 部分负荷率 | PLR | - | Q_evap/Q_rated |

##### 输出结果
| 参数 | 符号 | 单位 | 说明 |
|------|------|------|------|
| 压缩机功耗 | W_comp | MW | 基于COP |
| 冷凝器排热 | Q_cond | MW | Q_evap + W_comp |
| 性能系数 | COP | - | f(PLR, T_cw_in) |

##### 性能模型

基于**ASHRAE Standard 90.1 Appendix G**性能曲线：

```
COP = f(PLR, T_cw_in, T_chw_supply)

使用双二次多项式：
CapFT = a1 + b1·T_chw + c1·T_chw² + d1·T_cw + e1·T_cw² + f1·T_chw·T_cw
EIRFT = a2 + b2·T_chw + c2·T_chw² + d2·T_cw + e2·T_cw² + f2·T_chw·T_cw
EIRFPLR = a3 + b3·PLR + c3·PLR²

COP_actual = COP_rated / (EIRFT × EIRFPLR)
```

##### 能量平衡
```
Q_evap = ṁ_chw × c_p × (T_chw_return - T_chw_supply)
W_comp = Q_evap / COP
Q_cond = Q_evap + W_comp
Q_cond = ṁ_cw × c_p × (T_cw_out - T_cw_in)
```

##### 类结构
```python
class Chiller:
    def __init__(self, rated_capacity_mw, rated_cop):
        """初始化冷水机组"""
        self.performance_curves = self._load_ashrae_curves()

    def calculate_cop(self, plr, t_cw_in, t_chw_supply):
        """计算实际COP"""

    def calculate_power(self, q_evap, t_cw_in):
        """计算压缩机功耗"""

    def solve_energy_balance(self, q_evap, m_dot_chw, m_dot_cw):
        """求解能量平衡"""
```

#### 3.2 CoolingTower类（冷却塔）

##### 输入参数
| 参数 | 符号 | 单位 | 说明 |
|------|------|------|------|
| 冷凝器排热 | Q_cond | MW | 来自chiller |
| 循环水流量 | ṁ_cw | kg/s | 冷却水流量 |
| 入口水温 | T_in | °C | 来自chiller冷凝器 |
| 环境湿球温度 | T_wb | °C | 环境条件 |
| 浓缩倍数 | COC | - | 5 | Cycles of Concentration |

##### 输出结果
| 参数 | 符号 | 单位 | 说明 |
|------|------|------|------|
| 出口水温 | T_out | °C | 返回chiller |
| 风机功耗 | W_fan | MW | 冷却塔风机 |
| 蒸发水量 | ṁ_evap | kg/s | 蒸发损失 |
| 漂水损失 | ṁ_drift | kg/s | 0.001% × ṁ_cw |
| 排污水量 | ṁ_blowdown | kg/s | ṁ_evap/(COC-1) |
| 总补水量 | ṁ_makeup | kg/s | sum of above |

##### 热力学模型

**逼近度**（Approach）：
```
Approach = T_out - T_wb
典型值：3-5°C
```

**能量平衡**：
```
Q_cond = ṁ_cw × c_p × (T_in - T_out)
Q_cond = ṁ_evap × h_fg

其中：
- h_fg = 2260 kJ/kg - 水的汽化潜热
```

**水耗模型**：
```
蒸发损失：
ṁ_evap = Q_cond / h_fg
或使用经验公式：
ṁ_evap = 0.00153 × ΔT(°C) × ṁ_cw

漂水损失：
ṁ_drift = 0.00001 × ṁ_cw  (0.001%)

排污损失：
ṁ_blowdown = ṁ_evap / (COC - 1)

总补水：
ṁ_makeup = ṁ_evap + ṁ_drift + ṁ_blowdown
```

##### 类结构
```python
class CoolingTower:
    def __init__(self, approach_temp=4.0, coc=5.0):
        """初始化冷却塔"""

    def calculate_outlet_temp(self, t_wb, approach):
        """计算出口水温"""

    def calculate_water_consumption(self, q_cond, m_dot_cw, delta_t):
        """计算水耗"""

    def calculate_fan_power(self, q_cond, t_wb):
        """计算风机功耗（基于性能曲线）"""
```

---

## 系统集成与水环路

### 水环路定义

#### 环路1: 冷冻水环路 (Chilled Water Loop - CWL)
```
Chiller Evaporator → Building HXer → Compute HXer → Chiller Evaporator
```

**状态点**:
- **State 1**: 离开chiller蒸发器 (T=10°C)
- **State 2**: 经过Building HXer后
- **State 3**: 经过Compute HXer后
- **State 4**: 返回chiller蒸发器

#### 环路2: GPU冷却剂环路 (GPU Coolant Loop - GCL)
```
Compute HXer → Liquid Cooled GPUs → Compute HXer
```

**状态点**:
- **State 5**: 离开Compute HXer (T≈15°C)
- **State 6**: 经过GPU冷板后 (T≤40°C)
- **State 7**: 返回Compute HXer

#### 环路3: 冷却水环路 (Condenser Water Loop - CDWL)
```
Chiller Condenser → Cooling Tower → Chiller Condenser
```

**状态点**:
- **State 8**: 离开chiller冷凝器 (T高)
- **State 9**: 经过冷却塔后 (T=T_wb+approach)
- **State 10**: 返回chiller冷凝器

### 能量流向图

```
环境 (T_wb)
    ↓ (补水)
┌───────────────┐
│ Cooling Tower │ ← Q_cond + W_fan
└───────┬───────┘
        ↓ State 9 (冷却水)
┌───────────────┐
│    Chiller    │ ← W_comp
│  Condenser    │
└───────┬───────┘
        ↓ State 8
        ↑
        │ State 10
┌───────────────┐
│    Chiller    │
│  Evaporator   │
└───────┬───────┘
        ↓ State 1 (冷冻水10°C)
        │
    ┌───┴───┐
    ↓       ↓
Building  Compute
 HXer      HXer
    ↓       ↓
  风冷    GPU冷却水
  设备      环路
   ↓         ↓
 100MW    900MW
```

---

## 性能指标计算

### PUE (Power Usage Effectiveness)

**定义**:
```
PUE = 总设施功耗 / IT设备功耗

PUE = (P_IT + P_cooling) / P_IT
```

**组成部分**:
```
P_IT = 1000 MW  (1 GW)

P_cooling = W_comp + W_pumps + W_fans

其中：
- W_comp: 冷水机组压缩机功耗
- W_pumps: 各环路水泵功耗
- W_fans: 冷却塔风机功耗
```

**水泵功耗估算**:
```
基于行业数据：
- 冷冻水泵：~0.03 kW per kW cooling
- 冷却水泵：~0.02 kW per kW cooling
- GPU冷却水泵：~0.015 kW per kW cooling
```

### WUE (Water Usage Effectiveness)

**定义**:
```
WUE = 年总用水量(L) / IT设备年总能耗(kWh)

单位：L/kWh
```

**计算**:
```
年总用水量 = ṁ_makeup × 3600 × 8760 / 1000  (转换为L)
IT年总能耗 = P_IT × 8760  (kWh)

WUE = 年总用水量 / IT年总能耗
```

**行业基准**:
- 典型值：1.8 L/kWh
- 优秀值：< 1.0 L/kWh

---

## 设计参数表

### 系统假设与常数

| 参数 | 符号 | 数值 | 单位 | 来源 |
|------|------|------|------|------|
| 总IT负荷 | Q_IT | 1000 | MW | 项目要求 |
| 液冷比例 | - | 90 | % | 项目要求 |
| 风冷比例 | - | 10 | % | 项目要求 |
| GPU型号 | - | B200 | - | 选择 |
| GPU TDP | P_gpu | 1.2 | kW | 规格 |
| GPU数量 | N_gpu | 750,000 | 个 | 计算 |
| GPU冷却水入口 | T_gpu_in | 15 | °C | 设计 |
| GPU冷却水出口上限 | T_gpu_out_max | 40 | °C | 约束 |
| 建筑空气入口 | T_air_in | 20 | °C | 设计 |
| 建筑空气出口上限 | T_air_out_max | 25 | °C | 约束 |
| 冷冻水供水温度 | T_chw_supply | 10 | °C | 标准 |
| 冷却塔逼近度 | Approach | 4 | °C | 设计 |
| 环境湿球温度 | T_wb | 25.5 | °C | ASHRAE |
| 浓缩倍数（基准） | COC | 5 | - | 典型 |
| 漂水率 | drift_rate | 0.001 | % | 现代塔 |
| 水比热容 | c_p_water | 4.186 | kJ/(kg·K) | 物性 |
| 空气比热容 | c_p_air | 1.005 | kJ/(kg·K) | 物性 |
| 水汽化潜热 | h_fg | 2260 | kJ/kg | 物性 |
| 水密度 | ρ_water | 997 | kg/m³ | 物性 |

---

## 优化方案

### 基准方案 vs 优化方案

#### 基准方案（Baseline）
- 固定COC = 5
- 固定控制策略
- 恒定流量

#### 优化方案（Optimized）
**优化目标**: 最大化浓缩倍数以减少水耗

**策略**: 动态排污控制
```
允许最大浓度（以SiO2为例）：150 ppm
补水中SiO2浓度：25 ppm
最大COC = 150/25 = 6

减少排污：
ṁ_blowdown_baseline = ṁ_evap / (5-1) = 0.25 × ṁ_evap
ṁ_blowdown_optimized = ṁ_evap / (6-1) = 0.20 × ṁ_evap

节水比例 = (0.25 - 0.20)/0.25 = 20%
```

**成本权衡**:
- 更高COC需要更好的水处理
- 化学品成本增加
- 需要权衡水成本vs化学品成本

---

## 仿真流程

### 稳态求解算法

```
1. 初始化所有状态点温度（猜测值）

2. 给定环境条件：
   - T_wb = 25.5°C
   - IT负荷利用率

3. 计算热负荷：
   - Q_gpu = GPULoad.calculate_heat_load()
   - Q_building = BuildingLoad.calculate_heat_load()
   - Q_evap = Q_gpu + Q_building

4. 迭代求解环路：
   For iteration in range(max_iter):
       a. 计算chiller性能：
          - COP = Chiller.calculate_cop(PLR, T_cw_in)
          - W_comp = Q_evap / COP
          - Q_cond = Q_evap + W_comp

       b. 计算冷却塔：
          - T_cw_out = CoolingTower.calculate_outlet_temp(T_wb)
          - ṁ_makeup = CoolingTower.calculate_water_consumption()
          - W_fan = CoolingTower.calculate_fan_power()

       c. 计算温差：
          - 冷却水：ΔT_cw = Q_cond / (ṁ_cw × c_p)
          - 冷冻水：ΔT_chw = Q_evap / (ṁ_chw × c_p)
          - GPU水：ΔT_gpu = Q_gpu / (ṁ_gpu × c_p)

       d. 更新状态点温度

       e. 检查收敛：
          if |T_new - T_old| < tolerance:
              break

5. 计算性能指标：
   - PUE = (Q_IT + W_comp + W_pumps + W_fans) / Q_IT
   - WUE = ṁ_makeup / P_IT

6. 输出结果
```

### 变负荷仿真（24小时）

```
负荷曲线：
- 0-6时：60%负荷（夜间）
- 6-9时：80%负荷（早高峰）
- 9-18时：100%负荷（工作时间）
- 18-22时：90%负荷（晚高峰）
- 22-24时：70%负荷

环境条件曲线：
- T_wb随时间变化：20-28°C

对每个小时：
1. 更新负荷和环境条件
2. 运行稳态求解
3. 记录PUE, WUE, 各组件功耗
4. 存储结果

输出：
- 24小时PUE曲线
- 24小时WUE曲线
- 日平均PUE和WUE
```

---

## 代码架构

### 文件结构
```
615-thermodynamics-project/
├── src/
│   ├── __init__.py
│   ├── gpu_load.py          # GPU负荷模块
│   ├── building_load.py     # 建筑负荷模块
│   ├── hvac_system.py       # HVAC系统（Chiller + CoolingTower）
│   ├── heat_exchanger.py    # 热交换器（可选独立）
│   ├── datacenter.py        # 主系统集成
│   └── utils.py             # 工具函数（物性、单位转换等）
├── data/
│   ├── ashrae_curves.json   # ASHRAE性能曲线系数
│   ├── load_profiles.csv    # 24小时负荷曲线
│   └── weather.csv          # 环境温度数据
├── tests/
│   ├── test_gpu_load.py
│   ├── test_building_load.py
│   ├── test_hvac.py
│   └── test_datacenter.py
├── notebooks/
│   ├── analysis.ipynb       # 结果分析
│   └── visualization.ipynb  # 可视化
├── results/
│   └── output/
├── docs/
│   ├── claude.md            # 本文档
│   └── plan.md              # 执行计划
├── requirements.txt
└── main.py                  # 主运行脚本
```

### 依赖包
```
numpy>=1.24.0
pandas>=2.0.0
matplotlib>=3.7.0
scipy>=1.10.0
CoolProp>=6.5.0  # 用于精确水物性
```

---

## 输出与报告

### 结果输出

#### 数值结果
- 基准方案PUE和WUE
- 优化方案PUE和WUE
- 改进百分比
- 各组件功耗分解

#### 图表
1. 24小时PUE变化曲线
2. 24小时WUE变化曲线
3. 能量流向Sankey图
4. 各组件功耗饼图
5. 水耗分解图（蒸发/漂水/排污）
6. COP vs PLR曲线
7. 基准vs优化对比柱状图

### 报告结构（期刊格式）

```
1. Abstract
   - 问题、方法、结果、结论

2. Introduction
   - 背景：AI数据中心能耗和水耗挑战
   - 项目目标
   - 系统概述

3. System Model Development
   - 3.1 系统架构
   - 3.2 GPU负荷模型
   - 3.3 Building负荷模型
   - 3.4 HVAC系统模型
     - 3.4.1 Chiller性能模型
     - 3.4.2 Cooling Tower模型
   - 3.5 能量平衡方程
   - 3.6 假设表

4. Results: Baseline Performance
   - 4.1 设计点性能
   - 4.2 24小时仿真结果
   - 4.3 PUE分析
   - 4.4 WUE分析
   - 4.5 与行业基准比较

5. Discussion: Optimization and Implications
   - 5.1 优化策略：动态COC控制
   - 5.2 优化结果
   - 5.3 水-能源-成本权衡
   - 5.4 社会影响
     - 水资源压力
     - 环境可持续性
     - 政策建议

6. Conclusion
   - 主要发现
   - 优化效果总结
   - Future Work

7. References

8. Appendix
   - A: Python代码
   - B: ASHRAE曲线系数
   - C: 完整计算示例
```

---

## 验证与检查

### 能量守恒检查
```
总输入 = 总输出

输入：
- P_IT = 1000 MW

输出：
- Q_cond = Q_evap + W_comp
- 应等于 P_IT + W_comp

检查：Q_cond ≈ P_IT + W_comp（误差<1%）
```

### 质量守恒检查
```
冷却塔水平衡：
ṁ_makeup = ṁ_evap + ṁ_drift + ṁ_blowdown

检查各环路流量守恒
```

### 合理性检查
```
- PUE典型范围：1.2 - 1.8
- WUE典型范围：0.5 - 2.0 L/kWh
- COP典型范围：4.0 - 7.0
- 所有温度满足约束
```

---

## 关键技术挑战

### 1. 高热流密度
- B200 GPU热流密度 > 50 W/cm²
- 需要高效冷板设计
- 小温差、大流量

### 2. 系统耦合
- 三个环路相互耦合
- 需要迭代求解器
- 收敛性保证

### 3. 变负荷性能
- COP随PLR变化
- 部分负荷效率下降
- 控制策略影响

### 4. 水资源管理
- 蒸发损失不可避免
- COC与水质平衡
- 经济最优点

---

## 成功标准

### 技术标准
- [x] 所有能量平衡收敛（误差<1%）
- [x] 温度约束满足
- [x] PUE在合理范围
- [x] WUE计算正确

### 项目标准
- [x] 完整的系统模型
- [x] 基于真实设备数据
- [x] PUE和WUE计算
- [x] 优化方案实施
- [x] 社会影响讨论
- [x] 期刊格式报告

### 代码标准
- [x] 模块化设计
- [x] 清晰的接口
- [x] 完整的文档
- [x] 单元测试
- [x] 可复现的结果

---

## 参考资料

### 标准与规范
- ASHRAE Standard 90.1 - Energy Standard for Buildings
- ASHRAE Standard 205 - Representation of Performance Data
- CTI Standards - Cooling Tower Institute

### 设备数据
- NVIDIA GPU规格（B200, H100, GB200）
- 离心式冷水机组性能数据
- 冷却塔制造商数据表（SPX Marley等）

### 学术文献
- 数据中心能效研究
- 液冷技术进展
- 水资源可持续性

---

*本文档版本：1.0*
*最后更新：2025-11-06*
