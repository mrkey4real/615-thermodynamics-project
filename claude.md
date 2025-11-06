# 1 GW AI Datacenter Cooling System - Technical Implementation Guide

## Project Overview

**Objective**: Design and model a system-level cooling architecture for a 1 GW AI datacenter with energy balance calculations for each component, PUE/WUE analysis, and optimization strategies.

**Core Requirements** (from MEEN 615 project statement):
1. System-level thermodynamic model with energy balances
2. Component performance based on commercial equipment data
3. PUE and WUE estimation with societal impact analysis
4. Identification and implementation of optimization strategies
5. Deliverable in journal paper format

**System Scale**:
- Total IT Load: 1,000 MW (1 GW)
- Liquid-cooled GPU Load: 900 MW (90%)
- Air-cooled Equipment Load: 100 MW (10%)

**Critical Constraints**:
- GPU coolant temperature: T ≤ 40°C
- Building air temperature: T ≤ 25°C (human-compatible)

---

## System Architecture

### Component Topology

```
┌─────────────────────────────────────────────────────────────┐
│                    COOLING SYSTEM LOOP                       │
│                                                              │
│  Environment (T_wb) ──→ Makeup Water                         │
│         ↓                                                    │
│  ┌─────────────────┐                                        │
│  │ Cooling Tower   │ ← q = ṁh_fg (transpiration cooling)    │
│  │  - Evaporation  │                                        │
│  │  - Drift        │                                        │
│  │  - Blowdown     │                                        │
│  └────────┬────────┘                                        │
│           ↓ (Condenser Water Loop)                          │
│  ┌─────────────────┐                                        │
│  │    Chiller      │ ← W (compressor power)                 │
│  │  - Evaporator   │ → Q (cooling capacity)                 │
│  │  - Condenser    │                                        │
│  └────────┬────────┘                                        │
│           ↓ (Chilled Water Loop)                            │
│      ┌───┴────┐                                             │
│      ↓        ↓                                             │
│  ┌────────┐ ┌────────┐                                     │
│  │Building│ │Compute │                                     │
│  │  HXer  │ │  HXer  │                                     │
│  └───┬────┘ └───┬────┘                                     │
│      ↓          ↓                                           │
│  ┌────────┐ ┌────────────────┐                             │
│  │  Air   │ │ Liquid Cooled  │                             │
│  │ Cooled │ │  GPU Surfaces  │                             │
│  │  100MW │ │     900MW      │                             │
│  └────────┘ └────────────────┘                             │
│      ↓              ↓                                       │
│      Q              Q                                       │
└─────────────────────────────────────────────────────────────┘
```

### Energy Flow Hierarchy

```
IT Equipment (1000 MW)
    ↓
Heat Rejection to Coolant
    ↓
Heat Exchangers
    ↓
Chiller Evaporator (Q_evap)
    ↓
Chiller Compressor (+W_comp)
    ↓
Chiller Condenser (Q_cond = Q_evap + W_comp)
    ↓
Cooling Tower (evaporates water: q = ṁh_fg)
    ↓
Atmosphere
```

---

## State Point Definition

### Water/Coolant Loops

**Loop 1: Chilled Water Loop (CWL)**
```
Chiller Evaporator → Building HXer → Compute HXer → Return to Chiller
```
- State 1: Chiller evaporator outlet (T₁ ≈ 10°C, supply)
- State 2: After Building HXer (T₂ = T₁ + ΔT_building)
- State 3: After Compute HXer (T₃ = T₂ + ΔT_compute)
- State 4: Return to chiller (T₄ = T₃)

**Loop 2: GPU Coolant Loop (GCL)**
```
Compute HXer → GPU Cold Plates → Return to Compute HXer
```
- State 5: Compute HXer outlet to GPUs (T₅ ≈ 15°C)
- State 6: GPU cold plate outlet (T₆ ≤ 40°C, constraint)
- State 7: Return to Compute HXer (T₇ = T₆)

**Loop 3: Condenser Water Loop (CDW)**
```
Cooling Tower → Chiller Condenser → Return to Cooling Tower
```
- State 8: Cooling tower outlet (T₈ = T_wb + Approach)
- State 9: Chiller condenser outlet (T₉ = T₈ + ΔT_cond)
- State 10: Return to cooling tower (T₁₀ = T₉)

---

## Component Models

### 1. Liquid-Cooled GPU Module

**Class**: `GPULoad`

**Energy Balance**:
```
Q_GPU = ṁ_gpu × c_p × (T₆ - T₅)
```

**Implementation**:
```python
class GPULoad:
    """
    Models the thermal load from liquid-cooled GPU cluster.

    Energy Balance:
        Q = ṁ × c_p × ΔT

    Variables:
        Q_GPU: GPU heat load (W)
        ṁ_gpu: GPU coolant mass flow rate (kg/s)
        T_in: Inlet coolant temperature (°C) [State 5]
        T_out: Outlet coolant temperature (°C) [State 6]
        c_p: Specific heat of coolant (J/kg·K)
    """

    def __init__(self, gpu_model='NVIDIA B200', tdp_per_gpu=1200,
                 total_load_mw=900, max_temp=40.0):
        """
        Args:
            gpu_model: GPU identifier
            tdp_per_gpu: Thermal design power per GPU (W)
            total_load_mw: Total GPU thermal load (MW)
            max_temp: Maximum allowable coolant temperature (°C)
        """
        self.gpu_model = gpu_model
        self.tdp = tdp_per_gpu  # W per GPU
        self.total_load = total_load_mw * 1e6  # Convert to W
        self.max_temp = max_temp
        self.num_gpus = int(self.total_load / self.tdp)
        self.cp_water = 4186  # J/(kg·K)

    def calculate_heat_load(self, utilization=1.0):
        """
        Calculate actual heat load based on utilization.

        Args:
            utilization: GPU utilization factor (0-1)

        Returns:
            Q_actual: Actual heat load (W)
        """
        return self.total_load * utilization

    def calculate_outlet_temp(self, T_in, m_dot):
        """
        Calculate outlet coolant temperature from energy balance.

        Energy Balance: Q = ṁ × c_p × (T_out - T_in)
        Solve for: T_out = T_in + Q / (ṁ × c_p)

        Args:
            T_in: Inlet temperature (°C) [State 5]
            m_dot: Mass flow rate (kg/s)

        Returns:
            T_out: Outlet temperature (°C) [State 6]
        """
        Q = self.calculate_heat_load()
        delta_T = Q / (m_dot * self.cp_water)
        T_out = T_in + delta_T
        return T_out

    def check_temperature_constraint(self, T_out):
        """
        Verify outlet temperature meets constraint.

        Constraint: T_out ≤ 40°C

        Returns:
            bool: True if constraint satisfied
        """
        return T_out <= self.max_temp

    def calculate_required_flow_rate(self, T_in, T_out_target=40.0):
        """
        Calculate minimum flow rate to meet temperature constraint.

        From energy balance:
            ṁ_min = Q / (c_p × ΔT_max)

        Args:
            T_in: Inlet temperature (°C)
            T_out_target: Target outlet temperature (°C)

        Returns:
            m_dot_min: Minimum mass flow rate (kg/s)
        """
        Q = self.calculate_heat_load()
        delta_T_max = T_out_target - T_in
        m_dot_min = Q / (self.cp_water * delta_T_max)
        return m_dot_min

    def get_state_summary(self, T_in, m_dot):
        """
        Return complete state information.

        Returns:
            dict: State variables and energy balance
        """
        Q = self.calculate_heat_load()
        T_out = self.calculate_outlet_temp(T_in, m_dot)
        constraint_ok = self.check_temperature_constraint(T_out)

        return {
            'component': 'GPU Load',
            'num_gpus': self.num_gpus,
            'Q_load_MW': Q / 1e6,
            'm_dot_kg_s': m_dot,
            'T_in_C': T_in,
            'T_out_C': T_out,
            'delta_T_C': T_out - T_in,
            'constraint_satisfied': constraint_ok
        }
```

**Key Variables**:
| Symbol | Description | Units | Typical Value |
|--------|-------------|-------|---------------|
| Q_GPU | GPU heat load | MW | 900 |
| ṁ_gpu | GPU coolant flow | kg/s | ~9,000 |
| T₅ | Inlet temp (State 5) | °C | 15 |
| T₆ | Outlet temp (State 6) | °C | 35-40 |
| c_p | Water specific heat | J/(kg·K) | 4186 |
| N_GPU | Number of GPUs | - | 750,000 |

---

### 2. Building Air-Cooled Load Module

**Class**: `BuildingLoad`

**Energy Balance**:
```
Q_building = ṁ_air × c_p,air × (T_out - T_in)
```

**Implementation**:
```python
class BuildingLoad:
    """
    Models air-cooled equipment thermal load.

    Energy Balance:
        Q = ṁ_air × c_p,air × ΔT

    Variables:
        Q_building: Building equipment heat load (W)
        ṁ_air: Air mass flow rate (kg/s)
        T_air_in: Inlet air temperature (°C)
        T_air_out: Outlet air temperature (°C)
        c_p,air: Specific heat of air (J/kg·K)
    """

    def __init__(self, aircool_load_mw=100, max_temp=25.0):
        """
        Args:
            aircool_load_mw: Air-cooled equipment load (MW)
            max_temp: Maximum air temperature for human comfort (°C)
        """
        self.aircool_load = aircool_load_mw * 1e6  # Convert to W
        self.max_temp = max_temp
        self.cp_air = 1005  # J/(kg·K) at ~20°C

    def calculate_heat_load(self, utilization=1.0):
        """
        Calculate actual heat load.

        Returns:
            Q_actual: Heat load (W)
        """
        return self.aircool_load * utilization

    def calculate_outlet_temp(self, T_air_in, m_dot_air):
        """
        Calculate outlet air temperature.

        Energy Balance: Q = ṁ × c_p × (T_out - T_in)
        Solve for: T_out = T_in + Q / (ṁ × c_p)

        Args:
            T_air_in: Inlet air temperature (°C)
            m_dot_air: Air mass flow rate (kg/s)

        Returns:
            T_air_out: Outlet air temperature (°C)
        """
        Q = self.calculate_heat_load()
        delta_T = Q / (m_dot_air * self.cp_air)
        T_air_out = T_air_in + delta_T
        return T_air_out

    def check_temperature_constraint(self, T_air_out):
        """
        Verify air temperature constraint for human comfort.

        Constraint: T_air_out ≤ 25°C

        Returns:
            bool: True if constraint satisfied
        """
        return T_air_out <= self.max_temp

    def calculate_required_flow_rate(self, T_air_in, T_air_out_target=25.0):
        """
        Calculate minimum air flow rate.

        Returns:
            m_dot_air_min: Minimum air mass flow rate (kg/s)
        """
        Q = self.calculate_heat_load()
        delta_T_max = T_air_out_target - T_air_in
        m_dot_air_min = Q / (self.cp_air * delta_T_max)
        return m_dot_air_min
```

**Key Variables**:
| Symbol | Description | Units | Typical Value |
|--------|-------------|-------|---------------|
| Q_building | Building heat load | MW | 100 |
| ṁ_air | Air mass flow | kg/s | ~20,000 |
| T_air,in | Inlet air temp | °C | 20 |
| T_air,out | Outlet air temp | °C | ≤25 |
| c_p,air | Air specific heat | J/(kg·K) | 1005 |

---

### 3. Chiller Module

**Class**: `Chiller`

**Energy Balances**:

**Evaporator Side**:
```
Q_evap = ṁ_chw × c_p × (T_chw,return - T_chw,supply)
```

**Compressor**:
```
W_comp = Q_evap / COP
```

**Condenser Side**:
```
Q_cond = Q_evap + W_comp
Q_cond = ṁ_cw × c_p × (T_cw,out - T_cw,in)
```

**COP Model** (ASHRAE Standard 90.1 performance curves):
```
COP = f(PLR, T_cw,in, T_chw,supply)

Using performance curves:
    CapFT = a₁ + b₁·T_chw + c₁·T²_chw + d₁·T_cw + e₁·T²_cw + f₁·T_chw·T_cw
    EIRFT = a₂ + b₂·T_chw + c₂·T²_chw + d₂·T_cw + e₂·T²_cw + f₂·T_chw·T_cw
    EIRFPLR = a₃ + b₃·PLR + c₃·PLR²

    EIR = EIRFT × EIRFPLR / CapFT
    COP_actual = COP_rated / EIR
```

**Implementation**:
```python
import json
import numpy as np

class Chiller:
    """
    Models centrifugal water-cooled chiller using ASHRAE performance curves.

    Energy Balances:
        Evaporator: Q_evap = ṁ_chw × c_p × (T_return - T_supply)
        Compressor: W_comp = Q_evap / COP
        Condenser: Q_cond = Q_evap + W_comp

    Performance Model:
        COP = f(PLR, T_cw_in, T_chw_supply) using ASHRAE curves

    Variables:
        Q_evap: Evaporator cooling capacity (W)
        Q_cond: Condenser heat rejection (W)
        W_comp: Compressor power consumption (W)
        COP: Coefficient of performance (-)
        PLR: Part load ratio (-)
        ṁ_chw: Chilled water flow rate (kg/s)
        ṁ_cw: Condenser water flow rate (kg/s)
    """

    def __init__(self, rated_capacity_mw=1000, rated_cop=6.1,
                 t_chw_supply=10.0, curves_file='data/ashrae_curves.json'):
        """
        Args:
            rated_capacity_mw: Rated cooling capacity (MW)
            rated_cop: COP at rated conditions
            t_chw_supply: Chilled water supply temperature (°C)
            curves_file: Path to ASHRAE performance curve coefficients
        """
        self.rated_capacity = rated_capacity_mw * 1e6  # W
        self.rated_cop = rated_cop
        self.t_chw_supply = t_chw_supply
        self.cp_water = 4186  # J/(kg·K)

        # Load performance curves
        self.curves = self._load_performance_curves(curves_file)

    def _load_performance_curves(self, curves_file):
        """
        Load ASHRAE Standard 90.1 performance curve coefficients.

        Curves:
            - CapFT: Capacity as function of temperature
            - EIRFT: EIR as function of temperature
            - EIRFPLR: EIR as function of part load ratio

        Returns:
            dict: Curve coefficients
        """
        try:
            with open(curves_file, 'r') as f:
                curves = json.load(f)
            return curves
        except FileNotFoundError:
            # Default coefficients for centrifugal chiller (Path A from ASHRAE 90.1)
            return {
                'CapFT': {
                    'a': 0.9990653,
                    'b': -0.0009390,
                    'c': -0.0000360,
                    'd': 0.0014230,
                    'e': 0.0000440,
                    'f': -0.0002480
                },
                'EIRFT': {
                    'a': 0.5470531,
                    'b': -0.0137916,
                    'c': 0.0005135,
                    'd': 0.0095332,
                    'e': 0.0002617,
                    'f': -0.0005560
                },
                'EIRFPLR': {
                    'a': 0.0722504,
                    'b': 0.6033590,
                    'c': 0.3244080
                }
            }

    def calculate_cap_ft(self, t_chw_supply, t_cw_in):
        """
        Calculate capacity modifier based on temperatures.

        CapFT = a + b·T_chw + c·T²_chw + d·T_cw + e·T²_cw + f·T_chw·T_cw

        Args:
            t_chw_supply: Chilled water supply temperature (°C)
            t_cw_in: Condenser water inlet temperature (°C)

        Returns:
            cap_ft: Capacity modifier (-)
        """
        c = self.curves['CapFT']
        cap_ft = (c['a'] +
                  c['b'] * t_chw_supply +
                  c['c'] * t_chw_supply**2 +
                  c['d'] * t_cw_in +
                  c['e'] * t_cw_in**2 +
                  c['f'] * t_chw_supply * t_cw_in)
        return cap_ft

    def calculate_eir_ft(self, t_chw_supply, t_cw_in):
        """
        Calculate EIR temperature modifier.

        EIRFT = a + b·T_chw + c·T²_chw + d·T_cw + e·T²_cw + f·T_chw·T_cw

        Returns:
            eir_ft: EIR temperature modifier (-)
        """
        c = self.curves['EIRFT']
        eir_ft = (c['a'] +
                  c['b'] * t_chw_supply +
                  c['c'] * t_chw_supply**2 +
                  c['d'] * t_cw_in +
                  c['e'] * t_cw_in**2 +
                  c['f'] * t_chw_supply * t_cw_in)
        return eir_ft

    def calculate_eir_fplr(self, plr):
        """
        Calculate EIR part-load modifier.

        EIRFPLR = a + b·PLR + c·PLR²

        Args:
            plr: Part load ratio (0-1)

        Returns:
            eir_fplr: EIR part-load modifier (-)
        """
        c = self.curves['EIRFPLR']
        plr = np.clip(plr, 0.1, 1.0)  # Chillers typically don't operate below 10%
        eir_fplr = c['a'] + c['b'] * plr + c['c'] * plr**2
        return eir_fplr

    def calculate_cop(self, plr, t_cw_in, t_chw_supply=None):
        """
        Calculate actual COP at operating conditions.

        COP_actual = COP_rated / (EIRFT × EIRFPLR / CapFT)

        Args:
            plr: Part load ratio (-)
            t_cw_in: Condenser water inlet temperature (°C)
            t_chw_supply: Chilled water supply temperature (°C)

        Returns:
            cop_actual: Actual COP (-)
        """
        if t_chw_supply is None:
            t_chw_supply = self.t_chw_supply

        cap_ft = self.calculate_cap_ft(t_chw_supply, t_cw_in)
        eir_ft = self.calculate_eir_ft(t_chw_supply, t_cw_in)
        eir_fplr = self.calculate_eir_fplr(plr)

        eir = (eir_ft * eir_fplr) / cap_ft
        cop_actual = self.rated_cop / eir

        return cop_actual

    def calculate_power(self, q_evap, t_cw_in):
        """
        Calculate compressor power consumption.

        W_comp = Q_evap / COP

        Args:
            q_evap: Evaporator load (W)
            t_cw_in: Condenser water inlet temperature (°C)

        Returns:
            w_comp: Compressor power (W)
        """
        plr = q_evap / self.rated_capacity
        cop = self.calculate_cop(plr, t_cw_in)
        w_comp = q_evap / cop
        return w_comp

    def calculate_condenser_heat(self, q_evap, w_comp):
        """
        Calculate condenser heat rejection.

        Energy Balance: Q_cond = Q_evap + W_comp

        Args:
            q_evap: Evaporator load (W)
            w_comp: Compressor power (W)

        Returns:
            q_cond: Condenser heat rejection (W)
        """
        return q_evap + w_comp

    def solve_energy_balance(self, q_evap, m_dot_chw, m_dot_cw, t_cw_in):
        """
        Solve complete chiller energy balance.

        Args:
            q_evap: Evaporator load (W)
            m_dot_chw: Chilled water flow rate (kg/s)
            m_dot_cw: Condenser water flow rate (kg/s)
            t_cw_in: Condenser water inlet temp (°C)

        Returns:
            dict: Complete state information
        """
        # Calculate performance
        plr = q_evap / self.rated_capacity
        cop = self.calculate_cop(plr, t_cw_in)
        w_comp = self.calculate_power(q_evap, t_cw_in)
        q_cond = self.calculate_condenser_heat(q_evap, w_comp)

        # Calculate temperature differences
        delta_t_chw = q_evap / (m_dot_chw * self.cp_water)
        t_chw_return = self.t_chw_supply + delta_t_chw

        delta_t_cw = q_cond / (m_dot_cw * self.cp_water)
        t_cw_out = t_cw_in + delta_t_cw

        return {
            'component': 'Chiller',
            'Q_evap_MW': q_evap / 1e6,
            'Q_cond_MW': q_cond / 1e6,
            'W_comp_MW': w_comp / 1e6,
            'COP': cop,
            'PLR': plr,
            'T_chw_supply_C': self.t_chw_supply,
            'T_chw_return_C': t_chw_return,
            'T_cw_in_C': t_cw_in,
            'T_cw_out_C': t_cw_out,
            'delta_T_chw_C': delta_t_chw,
            'delta_T_cw_C': delta_t_cw
        }
```

**Key Variables**:
| Symbol | Description | Units | Typical Value |
|--------|-------------|-------|---------------|
| Q_evap | Evaporator load | MW | 1000 |
| Q_cond | Condenser heat | MW | ~1150 |
| W_comp | Compressor power | MW | ~150 |
| COP | Coefficient of performance | - | 5-7 |
| PLR | Part load ratio | - | 0.1-1.0 |
| T_chw,supply | CHW supply temp | °C | 10 |
| T_chw,return | CHW return temp | °C | ~15 |
| T_cw,in | Condenser water in | °C | ~29.5 |
| T_cw,out | Condenser water out | °C | ~35 |

---

### 4. Cooling Tower Module

**Class**: `CoolingTower`

**Energy Balance**:
```
Q_cond = ṁ_cw × c_p × (T_in - T_out)
Q_cond = ṁ_evap × h_fg  (evaporative cooling)
```

**Temperature Model**:
```
Approach = T_out - T_wb
Typical: Approach = 3-5°C

Range = T_in - T_out
```

**Water Balance**:
```
Evaporation: ṁ_evap = Q_cond / h_fg
             or ṁ_evap = 0.00153 × ΔT × ṁ_cw

Drift: ṁ_drift = drift_rate × ṁ_cw  (typically 0.001%)

Blowdown: ṁ_blowdown = ṁ_evap / (COC - 1)
          where COC = Cycles of Concentration

Makeup: ṁ_makeup = ṁ_evap + ṁ_drift + ṁ_blowdown
```

**Implementation**:
```python
class CoolingTower:
    """
    Models induced-draft cooling tower using transpiration cooling.

    Energy Balance:
        Q = ṁ_cw × c_p × (T_in - T_out)
        Q = ṁ_evap × h_fg

    Water Balance:
        ṁ_makeup = ṁ_evap + ṁ_drift + ṁ_blowdown
        ṁ_blowdown = ṁ_evap / (COC - 1)

    Variables:
        Q_cond: Heat rejection load (W)
        T_in: Inlet water temperature (°C) [State 9]
        T_out: Outlet water temperature (°C) [State 8]
        T_wb: Wet bulb temperature (°C)
        Approach: T_out - T_wb (°C)
        Range: T_in - T_out (°C)
        COC: Cycles of concentration (-)
        ṁ_evap: Evaporation loss (kg/s)
        ṁ_drift: Drift loss (kg/s)
        ṁ_blowdown: Blowdown loss (kg/s)
        ṁ_makeup: Total makeup water (kg/s)
    """

    def __init__(self, approach_temp=4.0, coc=5.0, drift_rate=0.00001):
        """
        Args:
            approach_temp: Approach temperature T_out - T_wb (°C)
            coc: Cycles of concentration (-)
            drift_rate: Drift as fraction of circulating water (-)
        """
        self.approach = approach_temp
        self.coc = coc
        self.drift_rate = drift_rate
        self.cp_water = 4186  # J/(kg·K)
        self.h_fg = 2260e3  # J/kg (latent heat at ~30°C)

    def calculate_outlet_temp(self, t_wb):
        """
        Calculate outlet water temperature.

        T_out = T_wb + Approach

        Args:
            t_wb: Wet bulb temperature (°C)

        Returns:
            t_out: Outlet water temperature (°C) [State 8]
        """
        return t_wb + self.approach

    def calculate_evaporation_rate(self, q_cond, m_dot_cw, delta_t):
        """
        Calculate evaporation water loss.

        Method 1 (energy-based): ṁ_evap = Q / h_fg
        Method 2 (empirical): ṁ_evap = 0.00153 × ΔT × ṁ_cw

        Using Method 1 for accuracy.

        Args:
            q_cond: Condenser heat rejection (W)
            m_dot_cw: Circulating water flow rate (kg/s)
            delta_t: Temperature range T_in - T_out (°C)

        Returns:
            m_evap: Evaporation rate (kg/s)
        """
        # Energy-based calculation
        m_evap = q_cond / self.h_fg
        return m_evap

    def calculate_drift_loss(self, m_dot_cw):
        """
        Calculate drift loss.

        Modern towers: 0.001% of circulating water

        Args:
            m_dot_cw: Circulating water flow rate (kg/s)

        Returns:
            m_drift: Drift loss (kg/s)
        """
        return self.drift_rate * m_dot_cw

    def calculate_blowdown_rate(self, m_evap):
        """
        Calculate blowdown requirement.

        Blowdown prevents mineral buildup.
        ṁ_blowdown = ṁ_evap / (COC - 1)

        Args:
            m_evap: Evaporation rate (kg/s)

        Returns:
            m_blowdown: Blowdown rate (kg/s)
        """
        return m_evap / (self.coc - 1)

    def calculate_makeup_water(self, m_evap, m_drift, m_blowdown):
        """
        Calculate total makeup water requirement.

        Water Balance: ṁ_makeup = ṁ_evap + ṁ_drift + ṁ_blowdown

        Returns:
            m_makeup: Total makeup water (kg/s)
        """
        return m_evap + m_drift + m_blowdown

    def calculate_fan_power(self, q_cond):
        """
        Estimate fan power consumption.

        Typical: 0.5-1.0% of heat rejection
        Using: 0.7% as baseline

        Args:
            q_cond: Heat rejection (W)

        Returns:
            w_fan: Fan power (W)
        """
        fan_power_fraction = 0.007
        return q_cond * fan_power_fraction

    def solve(self, q_cond, m_dot_cw, t_in, t_wb):
        """
        Solve complete cooling tower performance.

        Args:
            q_cond: Heat rejection load (W)
            m_dot_cw: Circulating water flow rate (kg/s)
            t_in: Inlet water temperature (°C) [State 9]
            t_wb: Ambient wet bulb temperature (°C)

        Returns:
            dict: Complete performance data
        """
        # Temperature calculations
        t_out = self.calculate_outlet_temp(t_wb)
        delta_t = t_in - t_out  # Range

        # Water consumption
        m_evap = self.calculate_evaporation_rate(q_cond, m_dot_cw, delta_t)
        m_drift = self.calculate_drift_loss(m_dot_cw)
        m_blowdown = self.calculate_blowdown_rate(m_evap)
        m_makeup = self.calculate_makeup_water(m_evap, m_drift, m_blowdown)

        # Power consumption
        w_fan = self.calculate_fan_power(q_cond)

        # Energy balance check
        q_check = m_dot_cw * self.cp_water * delta_t
        energy_balance_error = abs(q_cond - q_check) / q_cond * 100

        return {
            'component': 'Cooling Tower',
            'Q_cond_MW': q_cond / 1e6,
            'T_in_C': t_in,
            'T_out_C': t_out,
            'T_wb_C': t_wb,
            'Approach_C': self.approach,
            'Range_C': delta_t,
            'W_fan_MW': w_fan / 1e6,
            'm_evap_kg_s': m_evap,
            'm_drift_kg_s': m_drift,
            'm_blowdown_kg_s': m_blowdown,
            'm_makeup_kg_s': m_makeup,
            'm_makeup_L_s': m_makeup,  # 1 kg water ≈ 1 L
            'm_makeup_L_hr': m_makeup * 3600,
            'COC': self.coc,
            'energy_balance_error_pct': energy_balance_error
        }
```

**Key Variables**:
| Symbol | Description | Units | Typical Value |
|--------|-------------|-------|---------------|
| Q_cond | Heat rejection | MW | 1150 |
| T_in | Inlet water temp | °C | 35 |
| T_out | Outlet water temp | °C | 29.5 |
| T_wb | Wet bulb temp | °C | 25.5 |
| Approach | T_out - T_wb | °C | 4 |
| Range | T_in - T_out | °C | 5.5 |
| ṁ_evap | Evaporation | kg/s | ~500 |
| ṁ_makeup | Total makeup | kg/s | ~625 |
| COC | Concentration cycles | - | 5 |
| W_fan | Fan power | MW | ~8 |

---

## System Integration

### Main Datacenter Class

```python
class DataCenter:
    """
    Integrates all components into system-level model.

    System Energy Balance:
        P_IT = 1000 MW (heat input)
        Q_evap = Q_GPU + Q_building
        Q_cond = Q_evap + W_comp
        Heat to atmosphere via cooling tower

    Performance Metrics:
        PUE = (P_IT + P_cooling) / P_IT
        WUE = Annual water (L) / Annual IT energy (kWh)
    """

    def __init__(self, config=None):
        """
        Initialize datacenter system.

        Args:
            config: Configuration dictionary (optional)
        """
        # Default configuration
        if config is None:
            config = {
                'gpu_load_mw': 900,
                'building_load_mw': 100,
                'chiller_rated_cop': 6.1,
                'cooling_tower_approach': 4.0,
                'coc': 5.0,
                't_chw_supply': 10.0,
                't_gpu_in': 15.0,
                't_air_in': 20.0,
                't_wb_ambient': 25.5
            }
        self.config = config

        # Initialize components
        self.gpu_load = GPULoad(
            gpu_model='NVIDIA B200',
            tdp_per_gpu=1200,
            total_load_mw=config['gpu_load_mw']
        )

        self.building_load = BuildingLoad(
            aircool_load_mw=config['building_load_mw']
        )

        self.chiller = Chiller(
            rated_capacity_mw=1000,
            rated_cop=config['chiller_rated_cop'],
            t_chw_supply=config['t_chw_supply']
        )

        self.cooling_tower = CoolingTower(
            approach_temp=config['cooling_tower_approach'],
            coc=config['coc']
        )

        # Initialize state points
        self.state_points = self._initialize_state_points()

        # Calculate design flow rates
        self.flow_rates = self._calculate_design_flow_rates()

    def _initialize_state_points(self):
        """
        Initialize temperature state points with reasonable guesses.

        Returns:
            dict: Initial state point temperatures (°C)
        """
        return {
            'T1_chw_supply': self.config['t_chw_supply'],
            'T2_after_building_hx': 12.0,
            'T3_after_compute_hx': 15.0,
            'T4_chw_return': 15.0,
            'T5_gpu_supply': self.config['t_gpu_in'],
            'T6_gpu_return': 38.0,
            'T7_gpu_to_hx': 38.0,
            'T8_cw_from_tower': self.config['t_wb_ambient'] + self.config['cooling_tower_approach'],
            'T9_cw_from_chiller': 35.0,
            'T10_cw_to_chiller': 29.5
        }

    def _calculate_design_flow_rates(self):
        """
        Calculate design mass flow rates for all loops.

        Returns:
            dict: Flow rates (kg/s)
        """
        cp = 4186  # J/(kg·K)

        # GPU coolant loop
        # Q = ṁ × cp × ΔT, solve for ṁ
        q_gpu = self.config['gpu_load_mw'] * 1e6  # W
        delta_t_gpu = 25.0  # Conservative: 40°C - 15°C
        m_gpu = q_gpu / (cp * delta_t_gpu)

        # Chilled water loop
        q_evap = (self.config['gpu_load_mw'] + self.config['building_load_mw']) * 1e6
        delta_t_chw = 5.0  # Standard: 10°C supply, 15°C return
        m_chw = q_evap / (cp * delta_t_chw)

        # Condenser water loop (estimate)
        # Q_cond ≈ Q_evap × 1.15 (assuming COP~6)
        q_cond_estimate = q_evap * 1.15
        delta_t_cw = 5.5  # Typical range
        m_cw = q_cond_estimate / (cp * delta_t_cw)

        return {
            'm_gpu': m_gpu,
            'm_chw': m_chw,
            'm_cw': m_cw
        }

    def solve_steady_state(self, utilization=1.0, t_wb=None,
                          max_iter=100, tolerance=0.01):
        """
        Solve steady-state system energy balance.

        Iteration procedure:
        1. Calculate heat loads from IT equipment
        2. Calculate chiller performance
        3. Calculate cooling tower performance
        4. Update temperature state points
        5. Check convergence

        Args:
            utilization: IT equipment utilization (0-1)
            t_wb: Ambient wet bulb temperature (°C)
            max_iter: Maximum iterations
            tolerance: Convergence tolerance (°C)

        Returns:
            dict: Complete system solution
        """
        if t_wb is None:
            t_wb = self.config['t_wb_ambient']

        # Iteration loop
        for iteration in range(max_iter):
            state_old = self.state_points.copy()

            # Step 1: Calculate IT heat loads
            q_gpu = self.gpu_load.calculate_heat_load(utilization)
            q_building = self.building_load.calculate_heat_load(utilization)
            q_evap = q_gpu + q_building

            # Step 2: Calculate chiller performance
            t_cw_in = self.state_points['T8_cw_from_tower']
            chiller_result = self.chiller.solve_energy_balance(
                q_evap=q_evap,
                m_dot_chw=self.flow_rates['m_chw'],
                m_dot_cw=self.flow_rates['m_cw'],
                t_cw_in=t_cw_in
            )

            w_comp = chiller_result['W_comp_MW'] * 1e6
            q_cond = chiller_result['Q_cond_MW'] * 1e6
            cop = chiller_result['COP']

            # Step 3: Calculate cooling tower performance
            t_cw_from_chiller = self.state_points['T9_cw_from_chiller']
            tower_result = self.cooling_tower.solve(
                q_cond=q_cond,
                m_dot_cw=self.flow_rates['m_cw'],
                t_in=t_cw_from_chiller,
                t_wb=t_wb
            )

            # Step 4: Update state points
            # Chilled water loop
            self.state_points['T1_chw_supply'] = self.chiller.t_chw_supply
            self.state_points['T4_chw_return'] = chiller_result['T_chw_return_C']

            # Condenser water loop
            self.state_points['T8_cw_from_tower'] = tower_result['T_out_C']
            self.state_points['T9_cw_from_chiller'] = chiller_result['T_cw_out_C']
            self.state_points['T10_cw_to_chiller'] = self.state_points['T8_cw_from_tower']

            # GPU loop
            t_gpu_out = self.gpu_load.calculate_outlet_temp(
                T_in=self.config['t_gpu_in'],
                m_dot=self.flow_rates['m_gpu']
            )
            self.state_points['T6_gpu_return'] = t_gpu_out

            # Step 5: Check convergence
            max_change = max(
                abs(self.state_points[key] - state_old[key])
                for key in self.state_points
                if isinstance(self.state_points[key], (int, float))
            )

            if max_change < tolerance:
                print(f"✓ Converged after {iteration + 1} iterations (max ΔT = {max_change:.4f}°C)")
                break
        else:
            print(f"✗ Warning: Did not converge after {max_iter} iterations")

        # Calculate auxiliary power consumption
        w_pumps = self._calculate_pump_power(q_evap)
        w_fans = tower_result['W_fan_MW'] * 1e6

        # Compile results
        results = {
            'converged': max_change < tolerance,
            'iterations': iteration + 1,
            'utilization': utilization,
            'T_wb_C': t_wb,

            # Power flows
            'P_IT_MW': (q_gpu + q_building) / 1e6,
            'Q_evap_MW': q_evap / 1e6,
            'Q_cond_MW': q_cond / 1e6,
            'W_comp_MW': w_comp / 1e6,
            'W_pumps_MW': w_pumps / 1e6,
            'W_fans_MW': w_fans / 1e6,
            'W_cooling_total_MW': (w_comp + w_pumps + w_fans) / 1e6,

            # Performance metrics
            'COP': cop,
            'PLR': q_evap / self.chiller.rated_capacity,

            # Water consumption
            'm_makeup_kg_s': tower_result['m_makeup_kg_s'],
            'm_makeup_L_hr': tower_result['m_makeup_L_hr'],
            'm_evap_kg_s': tower_result['m_evap_kg_s'],
            'm_blowdown_kg_s': tower_result['m_blowdown_kg_s'],

            # State points
            'state_points': self.state_points.copy(),

            # Constraint checks
            'gpu_temp_ok': self.gpu_load.check_temperature_constraint(t_gpu_out),
            'T_gpu_out_C': t_gpu_out,

            # Energy balance check
            'energy_balance_error_pct': abs(q_cond - (q_evap + w_comp)) / q_cond * 100
        }

        return results

    def _calculate_pump_power(self, q_cooling):
        """
        Estimate pump power for all loops.

        Based on industry guidelines:
            - Chilled water pumps: 3% of cooling load
            - Condenser water pumps: 2% of cooling load
            - GPU coolant pumps: 1.5% of GPU load

        Args:
            q_cooling: Total cooling load (W)

        Returns:
            w_pumps_total: Total pump power (W)
        """
        q_gpu = self.gpu_load.total_load

        w_chw_pump = q_cooling * 0.03
        w_cw_pump = q_cooling * 0.02
        w_gpu_pump = q_gpu * 0.015

        return w_chw_pump + w_cw_pump + w_gpu_pump

    def calculate_pue(self, results):
        """
        Calculate Power Usage Effectiveness.

        PUE = Total Facility Power / IT Equipment Power
        PUE = (P_IT + P_cooling) / P_IT

        Args:
            results: Results dictionary from solve_steady_state()

        Returns:
            pue: Power Usage Effectiveness (-)
        """
        p_it = results['P_IT_MW']
        p_cooling = results['W_cooling_total_MW']
        p_total = p_it + p_cooling

        pue = p_total / p_it
        return pue

    def calculate_wue(self, results):
        """
        Calculate Water Usage Effectiveness.

        WUE = Annual water consumption (L) / Annual IT energy (kWh)

        Args:
            results: Results dictionary from solve_steady_state()

        Returns:
            wue: Water Usage Effectiveness (L/kWh)
        """
        # Annual water consumption
        m_makeup_kg_s = results['m_makeup_kg_s']
        annual_water_L = m_makeup_kg_s * 3600 * 8760  # kg ≈ L

        # Annual IT energy consumption
        p_it_kw = results['P_IT_MW'] * 1000
        annual_it_kwh = p_it_kw * 8760

        wue = annual_water_L / annual_it_kwh
        return wue

    def print_summary(self, results):
        """
        Print formatted results summary.
        """
        pue = self.calculate_pue(results)
        wue = self.calculate_wue(results)

        print("\n" + "="*70)
        print("DATACENTER COOLING SYSTEM - PERFORMANCE SUMMARY")
        print("="*70)

        print("\n--- IT LOAD ---")
        print(f"Total IT Load:        {results['P_IT_MW']:>8.1f} MW")
        print(f"GPU Load (90%):       {self.config['gpu_load_mw']:>8.1f} MW")
        print(f"Building Load (10%):  {self.config['building_load_mw']:>8.1f} MW")
        print(f"Number of GPUs:       {self.gpu_load.num_gpus:>8,}")

        print("\n--- COOLING SYSTEM POWER ---")
        print(f"Chiller Compressor:   {results['W_comp_MW']:>8.1f} MW")
        print(f"Pumps (all loops):    {results['W_pumps_MW']:>8.1f} MW")
        print(f"Cooling Tower Fans:   {results['W_fans_MW']:>8.1f} MW")
        print(f"Total Cooling:        {results['W_cooling_total_MW']:>8.1f} MW")

        print("\n--- PERFORMANCE METRICS ---")
        print(f"PUE:                  {pue:>8.3f}")
        print(f"Chiller COP:          {results['COP']:>8.2f}")
        print(f"Part Load Ratio:      {results['PLR']:>8.1f}%")

        print("\n--- WATER CONSUMPTION ---")
        print(f"Evaporation:          {results['m_evap_kg_s']:>8.1f} kg/s  ({results['m_evap_kg_s']*3600:>10,.0f} L/hr)")
        print(f"Blowdown:             {results['m_blowdown_kg_s']:>8.1f} kg/s  ({results['m_blowdown_kg_s']*3600:>10,.0f} L/hr)")
        print(f"Total Makeup:         {results['m_makeup_kg_s']:>8.1f} kg/s  ({results['m_makeup_L_hr']:>10,.0f} L/hr)")
        print(f"WUE:                  {wue:>8.3f} L/kWh")
        print(f"Annual Water:         {results['m_makeup_kg_s']*3600*8760/1e9:>8.1f} million m³/year")

        print("\n--- TEMPERATURES ---")
        print(f"GPU Coolant Out:      {results['T_gpu_out_C']:>8.1f}°C  (limit: 40°C) {'✓' if results['gpu_temp_ok'] else '✗'}")
        print(f"CHW Supply/Return:    {results['state_points']['T1_chw_supply']:>8.1f}°C / {results['state_points']['T4_chw_return']:.1f}°C")
        print(f"CW Range:             {results['state_points']['T9_cw_from_chiller'] - results['state_points']['T8_cw_from_tower']:>8.1f}°C")
        print(f"CT Approach:          {results['state_points']['T8_cw_from_tower'] - results['T_wb_C']:>8.1f}°C")

        print("\n--- VALIDATION ---")
        print(f"Energy Balance Error: {results['energy_balance_error_pct']:>8.4f}%")
        print(f"Convergence:          {'Yes' if results['converged'] else 'No'} ({results['iterations']} iterations)")

        print("="*70 + "\n")
```

---

## Optimization Strategy

### Baseline vs. Optimized Configuration

**Optimization Target**: Reduce water consumption (improve WUE)

**Strategy**: Increase Cycles of Concentration (COC)

**Technical Approach**:

```python
class CoolingTowerOptimized(CoolingTower):
    """
    Optimized cooling tower with dynamic COC control.

    Optimization Strategy:
        - Increase COC from 5 to maximum feasible value
        - Maximum COC limited by water chemistry (e.g., SiO2 concentration)
        - Reduce blowdown rate: ṁ_blowdown = ṁ_evap / (COC - 1)
    """

    def __init__(self, makeup_silica_ppm=25, max_silica_ppm=150, **kwargs):
        """
        Args:
            makeup_silica_ppm: SiO2 concentration in makeup water (ppm)
            max_silica_ppm: Maximum allowable SiO2 in circulating water (ppm)
            **kwargs: Pass through to base class
        """
        # Calculate maximum COC based on silica limit
        max_coc = max_silica_ppm / makeup_silica_ppm

        # Override COC if not specified
        if 'coc' not in kwargs:
            kwargs['coc'] = max_coc

        super().__init__(**kwargs)

        self.makeup_silica_ppm = makeup_silica_ppm
        self.max_silica_ppm = max_silica_ppm
        self.max_coc = max_coc

    def calculate_water_savings(self, baseline_coc=5.0):
        """
        Calculate water savings compared to baseline.

        Returns:
            dict: Water savings analysis
        """
        # Blowdown reduction
        # Baseline: ṁ_bd_baseline = ṁ_evap / (COC_base - 1)
        # Optimized: ṁ_bd_opt = ṁ_evap / (COC_opt - 1)

        bd_fraction_baseline = 1.0 / (baseline_coc - 1)
        bd_fraction_optimized = 1.0 / (self.coc - 1)

        reduction = (bd_fraction_baseline - bd_fraction_optimized) / bd_fraction_baseline

        return {
            'baseline_COC': baseline_coc,
            'optimized_COC': self.coc,
            'blowdown_reduction_pct': reduction * 100,
            'max_silica_limit_ppm': self.max_silica_ppm
        }
```

**Water Savings Calculation**:
```
Baseline (COC = 5):
    ṁ_blowdown = ṁ_evap / 4 = 0.25 × ṁ_evap

Optimized (COC = 6):
    ṁ_blowdown = ṁ_evap / 5 = 0.20 × ṁ_evap

Reduction = (0.25 - 0.20) / 0.25 = 20%

Makeup reduction: ~4-5% (since makeup = evap + drift + blowdown)
```

**Trade-offs**:
- **Benefit**: Reduced water consumption and operating cost
- **Cost**: Increased water treatment chemical cost
- **Requirement**: Enhanced water treatment system
- **Risk**: Scale formation if COC exceeds limits

---

## Performance Metrics

### PUE (Power Usage Effectiveness)

**Definition**:
```
PUE = Total Facility Power / IT Equipment Power

PUE = (P_IT + P_cooling) / P_IT

Where:
    P_IT = 1000 MW
    P_cooling = W_comp + W_pumps + W_fans
```

**Industry Benchmarks**:
- Typical datacenter: PUE = 1.6 - 1.8
- Good datacenter: PUE = 1.3 - 1.5
- Excellent datacenter: PUE = 1.1 - 1.2
- Theoretical minimum: PUE = 1.0 (no cooling overhead)

### WUE (Water Usage Effectiveness)

**Definition**:
```
WUE = Annual On-Site Water Usage (L) / IT Equipment Energy (kWh)

WUE = (ṁ_makeup × 3600 × 8760) / (P_IT × 8760)

Units: L/kWh
```

**Industry Benchmarks**:
- Typical (wet cooling): WUE = 1.5 - 2.0 L/kWh
- Good (optimized wet): WUE = 0.8 - 1.2 L/kWh
- Excellent (hybrid): WUE = 0.2 - 0.5 L/kWh
- Best (dry cooling): WUE < 0.1 L/kWh

---

## Code Structure

### File Organization

```
615-thermodynamics-project/
├── src/
│   ├── __init__.py
│   ├── gpu_load.py              # GPULoad class
│   ├── building_load.py         # BuildingLoad class
│   ├── hvac_system.py           # Chiller and CoolingTower classes
│   ├── datacenter.py            # DataCenter system integration
│   └── utils.py                 # Utility functions (unit conversions, validation)
│
├── data/
│   ├── ashrae_curves.json       # Chiller performance curve coefficients
│   ├── load_profiles.csv        # 24-hour utilization profiles
│   └── weather_data.csv         # Hourly wet bulb temperatures
│
├── tests/
│   ├── test_gpu_load.py         # Unit tests for GPU module
│   ├── test_building_load.py   # Unit tests for building module
│   ├── test_hvac.py             # Unit tests for HVAC components
│   └── test_datacenter.py       # Integration tests
│
├── scripts/
│   ├── run_baseline.py          # Run baseline scenario
│   ├── run_optimized.py         # Run optimized scenario
│   ├── run_24hour.py            # Run 24-hour simulation
│   └── compare_scenarios.py     # Compare baseline vs optimized
│
├── notebooks/
│   ├── analysis.ipynb           # Results analysis
│   └── visualization.ipynb      # Generate plots for paper
│
├── results/
│   └── output/                  # Simulation outputs (JSON, CSV)
│
├── doc/
│   ├── claude.md                # This document
│   └── MEEN 615 project statement.pdf
│
├── requirements.txt             # Python dependencies
├── README.md                    # Project overview
└── main.py                      # Main execution script
```

### Dependencies

```txt
numpy>=1.24.0
pandas>=2.0.0
matplotlib>=3.7.0
scipy>=1.10.0
CoolProp>=6.5.0
pytest>=7.0.0
jupyter>=1.0.0
```

---

## Main Execution Script

```python
# main.py

import json
import pandas as pd
import matplotlib.pyplot as plt
from src.datacenter import DataCenter
from src.hvac_system import CoolingTowerOptimized

def run_baseline_scenario():
    """
    Run baseline scenario (COC = 5).
    """
    print("\n" + "="*70)
    print("RUNNING BASELINE SCENARIO (COC = 5)")
    print("="*70)

    config = {
        'gpu_load_mw': 900,
        'building_load_mw': 100,
        'chiller_rated_cop': 6.1,
        'cooling_tower_approach': 4.0,
        'coc': 5.0,
        't_chw_supply': 10.0,
        't_gpu_in': 15.0,
        't_air_in': 20.0,
        't_wb_ambient': 25.5
    }

    dc = DataCenter(config)
    results = dc.solve_steady_state(utilization=1.0)
    dc.print_summary(results)

    # Save results
    with open('results/baseline_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)

    return results

def run_optimized_scenario():
    """
    Run optimized scenario (COC = 6).
    """
    print("\n" + "="*70)
    print("RUNNING OPTIMIZED SCENARIO (COC = 6)")
    print("="*70)

    config = {
        'gpu_load_mw': 900,
        'building_load_mw': 100,
        'chiller_rated_cop': 6.1,
        'cooling_tower_approach': 4.0,
        'coc': 6.0,  # Optimized
        't_chw_supply': 10.0,
        't_gpu_in': 15.0,
        't_air_in': 20.0,
        't_wb_ambient': 25.5
    }

    dc = DataCenter(config)
    results = dc.solve_steady_state(utilization=1.0)
    dc.print_summary(results)

    # Save results
    with open('results/optimized_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)

    return results

def compare_scenarios(baseline, optimized):
    """
    Compare baseline vs optimized scenarios.
    """
    print("\n" + "="*70)
    print("SCENARIO COMPARISON")
    print("="*70)

    # Calculate metrics
    pue_base = baseline['P_IT_MW'] + baseline['W_cooling_total_MW']
    pue_base /= baseline['P_IT_MW']

    pue_opt = optimized['P_IT_MW'] + optimized['W_cooling_total_MW']
    pue_opt /= optimized['P_IT_MW']

    wue_base = (baseline['m_makeup_kg_s'] * 3600 * 8760) / (baseline['P_IT_MW'] * 1000 * 8760)
    wue_opt = (optimized['m_makeup_kg_s'] * 3600 * 8760) / (optimized['P_IT_MW'] * 1000 * 8760)

    water_savings_pct = (baseline['m_makeup_kg_s'] - optimized['m_makeup_kg_s']) / baseline['m_makeup_kg_s'] * 100

    print(f"\n{'Metric':<30} {'Baseline':>15} {'Optimized':>15} {'Change':>15}")
    print("-" * 77)
    print(f"{'COC':<30} {5.0:>15.1f} {6.0:>15.1f} {'+20%':>15}")
    print(f"{'PUE':<30} {pue_base:>15.3f} {pue_opt:>15.3f} {(pue_opt-pue_base):>+15.4f}")
    print(f"{'WUE (L/kWh)':<30} {wue_base:>15.3f} {wue_opt:>15.3f} {(wue_opt-wue_base):>+15.4f}")
    print(f"{'Makeup Water (kg/s)':<30} {baseline['m_makeup_kg_s']:>15.1f} {optimized['m_makeup_kg_s']:>15.1f} {-water_savings_pct:>+14.1f}%")
    print(f"{'Evaporation (kg/s)':<30} {baseline['m_evap_kg_s']:>15.1f} {optimized['m_evap_kg_s']:>15.1f} {'0%':>15}")
    print(f"{'Blowdown (kg/s)':<30} {baseline['m_blowdown_kg_s']:>15.1f} {optimized['m_blowdown_kg_s']:>15.1f} {-((baseline['m_blowdown_kg_s']-optimized['m_blowdown_kg_s'])/baseline['m_blowdown_kg_s']*100):>+14.1f}%")

    annual_water_savings_m3 = water_savings_pct / 100 * baseline['m_makeup_kg_s'] * 3600 * 8760 / 1000
    print(f"\n{'Annual Water Savings:':<30} {annual_water_savings_m3:>15,.0f} m³/year")
    print("="*70 + "\n")

if __name__ == "__main__":
    # Run scenarios
    baseline_results = run_baseline_scenario()
    optimized_results = run_optimized_scenario()

    # Compare
    compare_scenarios(baseline_results, optimized_results)
```

---

## Deliverable: Journal Paper Structure

### Required Sections (per project statement)

**1. Abstract** (150-200 words)
- Problem: 1 GW AI datacenter cooling challenge
- Method: System-level thermodynamic modeling
- Key results: PUE, WUE values
- Conclusion: Optimization impact

**2. Introduction** (2-3 pages)
- Background: AI datacenter growth and thermal challenges
- Liquid cooling necessity for modern GPUs
- Water consumption concerns
- Research objectives (Tasks 1-4 from project statement)

**3. System Model Development** (5-6 pages)
- 3.1 System Architecture
  - Component diagram (from project statement)
  - State point definition
  - Energy flow topology

- 3.2 Component Models
  - 3.2.1 Liquid-Cooled GPU Load
    - Energy balance equations
    - NVIDIA B200 specifications
    - Temperature constraints

  - 3.2.2 Air-Cooled Building Load
    - Energy balance
    - Human comfort requirements

  - 3.2.3 Chiller System
    - Refrigeration cycle overview
    - ASHRAE performance curves
    - COP calculation methodology
    - Energy balances (evaporator, compressor, condenser)

  - 3.2.4 Cooling Tower
    - Transpiration cooling physics (q = ṁh_fg)
    - Water balance model
    - Approach temperature
    - Cycles of concentration

- 3.3 System Integration
  - Water loops definition
  - Steady-state solution algorithm
  - Convergence criteria

- 3.4 Assumptions and Input Parameters
  - Table of all assumptions with sources
  - Equipment specifications (commercial data sources)
  - Ambient conditions

**4. Results: Baseline Performance** (3-4 pages)
- 4.1 Design Point Analysis
  - Full load (100% utilization) results
  - Energy flow breakdown
  - Temperature profile through system
  - Validation of energy/mass balances

- 4.2 Performance Metrics
  - PUE calculation and breakdown
  - WUE calculation
  - Comparison to industry benchmarks

- 4.3 Water Consumption Analysis
  - Evaporation, drift, blowdown breakdown
  - Annual water consumption
  - Equivalent to municipal water usage

**5. Discussion: Optimization and Implications** (4-5 pages)
- 5.1 Optimization Strategy
  - Identified component: Cooling tower COC
  - Technical approach: Increase COC from 5 to 6
  - Implementation requirements

- 5.2 Optimized Performance Results
  - Comparison table: baseline vs. optimized
  - Water savings quantification
  - WUE improvement
  - Cost-benefit analysis (chemical treatment vs. water cost)

- 5.3 Societal Implications (Task 3 requirement)
  - Water stress in datacenter regions
  - 1 GW facility impact on local water resources
  - Environmental sustainability considerations
  - Policy recommendations
  - Alternative cooling technologies (dry cooling, hybrid)

- 5.4 Sensitivity Analysis
  - Impact of ambient wet bulb temperature
  - Part-load performance
  - COP variation effects

**6. Conclusion** (1 page)
- System model successfully developed (Task 1 complete)
- PUE and WUE quantified (Task 3 complete)
- Optimization identified and implemented (Task 4 complete)
- Key findings summary
- Future work: dynamic optimization, alternative cooling methods

**7. References** (30+ citations)
- ASHRAE standards and handbooks
- NVIDIA GPU specifications
- Datacenter industry reports
- Academic literature on cooling systems
- Water resources and sustainability studies

**8. Appendices**
- Appendix A: Complete Python code
- Appendix B: ASHRAE performance curve coefficients
- Appendix C: Sample calculation walkthrough
- Appendix D: Complete list of variables and nomenclature

---

## Validation Checklist

### Energy Balance Validation

```python
def validate_energy_balance(results):
    """
    Verify energy conservation throughout system.
    """
    q_it = results['P_IT_MW'] * 1e6
    q_evap = results['Q_evap_MW'] * 1e6
    q_cond = results['Q_cond_MW'] * 1e6
    w_comp = results['W_comp_MW'] * 1e6

    # Check 1: Q_evap ≈ Q_IT
    error_1 = abs(q_evap - q_it) / q_it * 100

    # Check 2: Q_cond ≈ Q_evap + W_comp
    error_2 = abs(q_cond - (q_evap + w_comp)) / q_cond * 100

    print("Energy Balance Validation:")
    print(f"  Q_IT vs Q_evap error:           {error_1:.4f}% (should be <1%)")
    print(f"  Q_cond vs (Q_evap + W_comp):    {error_2:.4f}% (should be <1%)")

    return error_1 < 1.0 and error_2 < 1.0
```

### Physical Constraints

```python
def validate_constraints(results, state_points):
    """
    Verify all physical and operational constraints.
    """
    checks = {
        'GPU temp ≤ 40°C': state_points['T6_gpu_return'] <= 40.0,
        'All temps > 0°C': all(T > 0 for T in state_points.values()),
        'All temps < 100°C': all(T < 100 for T in state_points.values()),
        'PUE > 1.0': calculate_pue(results) > 1.0,
        'PUE < 2.0': calculate_pue(results) < 2.0,
        'COP > 0': results['COP'] > 0,
        'COP < 10': results['COP'] < 10,
        'WUE > 0': calculate_wue(results) > 0
    }

    print("\nConstraint Validation:")
    for check, passed in checks.items():
        status = "✓" if passed else "✗"
        print(f"  {status} {check}")

    return all(checks.values())
```

---

## Expected Results (Approximate)

### Baseline Scenario
- **PUE**: ~1.15 - 1.20
- **WUE**: ~0.6 - 0.8 L/kWh
- **Chiller COP**: ~6.0 - 6.5
- **Makeup Water**: ~600 - 650 kg/s (~21 million m³/year)
- **Cooling Power**: ~150 - 200 MW

### Optimized Scenario (COC = 6)
- **WUE**: ~0.55 - 0.75 L/kWh (4-5% improvement)
- **Water Savings**: ~4-5% (~1 million m³/year)
- **PUE**: Similar to baseline (~1.15 - 1.20)

### Societal Context
- 1 GW facility annual water consumption: ~20-25 million m³
- Equivalent to a city of ~100,000 - 150,000 people
- Significant regional water resource impact

---

## Implementation Notes

### Critical Success Factors

1. **Accurate Component Models**
   - Use validated ASHRAE performance curves
   - Base assumptions on commercial equipment specifications
   - Document all data sources

2. **Robust Solver**
   - Implement relaxation for convergence
   - Use reasonable initial guesses
   - Include convergence monitoring

3. **Thorough Validation**
   - Energy balance closure < 1% error
   - All temperatures physically reasonable
   - Results match industry benchmarks

4. **Clear Documentation**
   - Every equation numbered and explained
   - All variables defined in nomenclature
   - Assumptions table with justifications

### Common Pitfalls to Avoid

1. **Unit Inconsistency**
   - Always work in SI units internally (W, kg/s, °C, J)
   - Convert MW/kW only for display
   - Document all conversions

2. **Convergence Issues**
   - Use good initial guesses based on typical operating conditions
   - Implement under-relaxation if needed
   - Check for physical impossibilities

3. **Missing Energy Terms**
   - Don't forget pump power
   - Don't forget fan power
   - Account for all auxiliary loads

4. **Unrealistic Assumptions**
   - Verify all assumptions against industry data
   - When in doubt, be conservative
   - Cite sources for all equipment data

---

## Quick Start Guide

### Minimal Working Example

```python
from src.datacenter import DataCenter

# Create datacenter with default configuration
dc = DataCenter()

# Solve for steady-state at full load
results = dc.solve_steady_state(utilization=1.0, t_wb=25.5)

# Display results
dc.print_summary(results)

# Calculate metrics
pue = dc.calculate_pue(results)
wue = dc.calculate_wue(results)

print(f"\nPUE = {pue:.3f}")
print(f"WUE = {wue:.3f} L/kWh")
```

This document provides the complete technical foundation for implementing the MEEN 615 project. Focus on accuracy, validation, and clear presentation of results in the journal paper format.

---

**Document Version**: 2.0 (Technical Implementation Guide)
**Last Updated**: 2025-11-06
**Project Deadline**: 2025-12-01
