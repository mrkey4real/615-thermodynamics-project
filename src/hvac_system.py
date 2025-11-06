"""
HVAC System Module

Contains Chiller and CoolingTower classes for datacenter cooling system.
"""

import json
import os
import numpy as np


class Chiller:
    """
    Models centrifugal water-cooled chiller using ASHRAE performance curves.

    Energy Balances:
        Evaporator: Q_evap = m_dot_chw * cp * (T_return - T_supply)
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
        m_dot_chw: Chilled water flow rate (kg/s)
        m_dot_cw: Condenser water flow rate (kg/s)
    """

    def __init__(self, rated_capacity_mw, rated_cop, t_chw_supply, curves_file=None):
        """
        Initialize chiller module.

        Args:
            rated_capacity_mw: Rated cooling capacity (MW)
            rated_cop: COP at rated conditions
            t_chw_supply: Chilled water supply temperature (C)
            curves_file: Path to ASHRAE performance curve coefficients (optional)

        Raises:
            ValueError: If parameters are invalid
        """
        if rated_capacity_mw <= 0:
            raise ValueError(f"Invalid rated_capacity_mw: {rated_capacity_mw}, must be > 0")
        if rated_cop <= 0 or rated_cop > 10:
            raise ValueError(f"Invalid rated_cop: {rated_cop}, must be between 0 and 10")
        if t_chw_supply < 0 or t_chw_supply >= 30:
            raise ValueError(f"Invalid t_chw_supply: {t_chw_supply}, must be between 0 and 30 C")

        self.rated_capacity = rated_capacity_mw * 1e6  # W
        self.rated_cop = rated_cop
        self.t_chw_supply = t_chw_supply
        self.cp_water = 4186  # J/(kg-K)

        # Load performance curves
        self.curves = self._load_performance_curves(curves_file)

    def _load_performance_curves(self, curves_file):
        """
        Load ASHRAE Standard 90.1 performance curve coefficients.

        Curves:
            - CapFT: Capacity as function of temperature
            - EIRFT: EIR as function of temperature
            - EIRFPLR: EIR as function of part load ratio

        Args:
            curves_file: Path to JSON file with curve coefficients

        Returns:
            dict: Curve coefficients
        """
        if curves_file and os.path.exists(curves_file):
            try:
                with open(curves_file, 'r') as f:
                    curves = json.load(f)
                return curves
            except (json.JSONDecodeError, IOError) as e:
                raise ValueError(f"Failed to load curves from {curves_file}: {e}")

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

        CapFT = a + b*T_chw + c*T_chw^2 + d*T_cw + e*T_cw^2 + f*T_chw*T_cw

        Args:
            t_chw_supply: Chilled water supply temperature (C)
            t_cw_in: Condenser water inlet temperature (C)

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

        EIRFT = a + b*T_chw + c*T_chw^2 + d*T_cw + e*T_cw^2 + f*T_chw*T_cw

        Args:
            t_chw_supply: Chilled water supply temperature (C)
            t_cw_in: Condenser water inlet temperature (C)

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

        EIRFPLR = a + b*PLR + c*PLR^2

        Args:
            plr: Part load ratio (0-1)

        Returns:
            eir_fplr: EIR part-load modifier (-)
        """
        c = self.curves['EIRFPLR']
        # Chillers typically don't operate below 10%
        plr = np.clip(plr, 0.1, 1.0)
        eir_fplr = c['a'] + c['b'] * plr + c['c'] * plr**2
        return eir_fplr

    def calculate_cop(self, plr, t_cw_in, t_chw_supply=None):
        """
        Calculate actual COP at operating conditions.

        COP_actual = COP_rated / (EIRFT * EIRFPLR / CapFT)

        Args:
            plr: Part load ratio (-)
            t_cw_in: Condenser water inlet temperature (C)
            t_chw_supply: Chilled water supply temperature (C), defaults to self.t_chw_supply

        Returns:
            cop_actual: Actual COP (-)

        Raises:
            ValueError: If parameters are invalid
        """
        if not 0.0 <= plr <= 1.0:
            raise ValueError(f"Invalid plr: {plr}, must be between 0 and 1")

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
            t_cw_in: Condenser water inlet temperature (C)

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
            t_cw_in: Condenser water inlet temp (C)

        Returns:
            dict: Complete state information

        Raises:
            ValueError: If parameters are invalid
        """
        if q_evap <= 0:
            raise ValueError(f"Invalid q_evap: {q_evap}, must be > 0")
        if m_dot_chw <= 0:
            raise ValueError(f"Invalid m_dot_chw: {m_dot_chw}, must be > 0")
        if m_dot_cw <= 0:
            raise ValueError(f"Invalid m_dot_cw: {m_dot_cw}, must be > 0")

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


class CoolingTower:
    """
    Models induced-draft cooling tower using transpiration cooling.

    Energy Balance:
        Q = m_dot_cw * cp * (T_in - T_out)
        Q = m_evap * h_fg

    Water Balance:
        m_makeup = m_evap + m_drift + m_blowdown
        m_blowdown = m_evap / (COC - 1)

    Variables:
        Q_cond: Heat rejection load (W)
        T_in: Inlet water temperature (C) [State 9]
        T_out: Outlet water temperature (C) [State 8]
        T_wb: Wet bulb temperature (C)
        Approach: T_out - T_wb (C)
        Range: T_in - T_out (C)
        COC: Cycles of concentration (-)
        m_evap: Evaporation loss (kg/s)
        m_drift: Drift loss (kg/s)
        m_blowdown: Blowdown loss (kg/s)
        m_makeup: Total makeup water (kg/s)
    """

    def __init__(self, approach_temp, coc, drift_rate=0.00001):
        """
        Initialize cooling tower module.

        Args:
            approach_temp: Approach temperature T_out - T_wb (C)
            coc: Cycles of concentration (-)
            drift_rate: Drift as fraction of circulating water (-)

        Raises:
            ValueError: If parameters are invalid
        """
        if approach_temp <= 0 or approach_temp > 20:
            raise ValueError(f"Invalid approach_temp: {approach_temp}, must be between 0 and 20 C")
        if coc < 2 or coc > 10:
            raise ValueError(f"Invalid coc: {coc}, must be between 2 and 10")
        if drift_rate < 0 or drift_rate > 0.01:
            raise ValueError(f"Invalid drift_rate: {drift_rate}, must be between 0 and 0.01")

        self.approach = approach_temp
        self.coc = coc
        self.drift_rate = drift_rate
        self.cp_water = 4186  # J/(kg-K)
        self.h_fg = 2260e3  # J/kg (latent heat at ~30 C)

    def calculate_outlet_temp(self, t_wb):
        """
        Calculate outlet water temperature.

        T_out = T_wb + Approach

        Args:
            t_wb: Wet bulb temperature (C)

        Returns:
            t_out: Outlet water temperature (C) [State 8]

        Raises:
            ValueError: If t_wb is invalid
        """
        if t_wb < -20 or t_wb > 50:
            raise ValueError(f"Invalid t_wb: {t_wb}, must be between -20 and 50 C")

        return t_wb + self.approach

    def calculate_evaporation_rate(self, q_cond, m_dot_cw, delta_t):
        """
        Calculate evaporation water loss.

        Method 1 (energy-based): m_evap = Q / h_fg
        Method 2 (empirical): m_evap = 0.00153 * delta_T * m_dot_cw

        Using Method 1 for accuracy.

        Args:
            q_cond: Condenser heat rejection (W)
            m_dot_cw: Circulating water flow rate (kg/s)
            delta_t: Temperature range T_in - T_out (C)

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
        m_blowdown = m_evap / (COC - 1)

        Args:
            m_evap: Evaporation rate (kg/s)

        Returns:
            m_blowdown: Blowdown rate (kg/s)
        """
        return m_evap / (self.coc - 1)

    def calculate_makeup_water(self, m_evap, m_drift, m_blowdown):
        """
        Calculate total makeup water requirement.

        Water Balance: m_makeup = m_evap + m_drift + m_blowdown

        Args:
            m_evap: Evaporation rate (kg/s)
            m_drift: Drift loss (kg/s)
            m_blowdown: Blowdown rate (kg/s)

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
            t_in: Inlet water temperature (C) [State 9]
            t_wb: Ambient wet bulb temperature (C)

        Returns:
            dict: Complete performance data

        Raises:
            ValueError: If parameters are invalid
        """
        if q_cond <= 0:
            raise ValueError(f"Invalid q_cond: {q_cond}, must be > 0")
        if m_dot_cw <= 0:
            raise ValueError(f"Invalid m_dot_cw: {m_dot_cw}, must be > 0")
        if t_in < 0 or t_in >= 100:
            raise ValueError(f"Invalid t_in: {t_in}, must be between 0 and 100 C")

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


class CoolingTowerOptimized(CoolingTower):
    """
    Optimized cooling tower with dynamic COC control.

    Optimization Strategy:
        - Increase COC from 5 to maximum feasible value
        - Maximum COC limited by water chemistry (e.g., SiO2 concentration)
        - Reduce blowdown rate: m_blowdown = m_evap / (COC - 1)
    """

    def __init__(self, makeup_silica_ppm=25, max_silica_ppm=150, **kwargs):
        """
        Initialize optimized cooling tower.

        Args:
            makeup_silica_ppm: SiO2 concentration in makeup water (ppm)
            max_silica_ppm: Maximum allowable SiO2 in circulating water (ppm)
            **kwargs: Pass through to base class

        Raises:
            ValueError: If parameters are invalid
        """
        if makeup_silica_ppm <= 0 or makeup_silica_ppm > 100:
            raise ValueError(f"Invalid makeup_silica_ppm: {makeup_silica_ppm}, must be between 0 and 100")
        if max_silica_ppm <= makeup_silica_ppm:
            raise ValueError(f"max_silica_ppm ({max_silica_ppm}) must be > makeup_silica_ppm ({makeup_silica_ppm})")

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

        Args:
            baseline_coc: Baseline cycles of concentration

        Returns:
            dict: Water savings analysis
        """
        # Blowdown reduction
        # Baseline: m_bd_baseline = m_evap / (COC_base - 1)
        # Optimized: m_bd_opt = m_evap / (COC_opt - 1)

        bd_fraction_baseline = 1.0 / (baseline_coc - 1)
        bd_fraction_optimized = 1.0 / (self.coc - 1)

        reduction = (bd_fraction_baseline - bd_fraction_optimized) / bd_fraction_baseline

        return {
            'baseline_COC': baseline_coc,
            'optimized_COC': self.coc,
            'blowdown_reduction_pct': reduction * 100,
            'max_silica_limit_ppm': self.max_silica_ppm
        }
