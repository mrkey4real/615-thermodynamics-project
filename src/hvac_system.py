"""
HVAC System Module

Contains Chiller and CoolingTower classes for datacenter cooling system.

Refactored to use component-level thermodynamic modeling:
- Chiller: Full refrigeration cycle with heat exchanger energy balances
- CoolingTower: Psychrometric analysis with air/water mass/energy balances
"""

import json
import os
import numpy as np
from .refrigerant_cycle import VaporCompressionCycle, HeatExchanger, COOLPROP_AVAILABLE
from .psychrometrics import MoistAir, PsychrometricState


class Chiller:
    """
    Models water-cooled chiller using full vapor compression refrigeration cycle.

    Component-Level Modeling:
        - Refrigerant cycle: Compressor, condenser, expansion valve, evaporator
        - Evaporator HX: Matches refrigerant-side and chilled-water-side energy
        - Condenser HX: Matches refrigerant-side and condenser-water-side energy
        - Iterative solution for consistent evaporator/condenser temperatures

    Thermodynamic States:
        Refrigerant side: States 1-4 (evap out, comp out, cond out, valve out)
        Chilled water: T_in, T_out, mass flow
        Condenser water: T_in, T_out, mass flow

    Energy Balances:
        Evaporator: Q_evap_ref = m_ref*(h1-h4) = m_chw*cp*(T_chw_in - T_chw_out)
        Condenser: Q_cond_ref = m_ref*(h2-h3) = m_cw*cp*(T_cw_out - T_cw_in)
        Compressor: W_comp = m_ref*(h2-h1)
        Overall: Q_cond = Q_evap + W_comp

    Variables:
        m_dot_ref: Refrigerant mass flow rate (kg/s)
        m_dot_chw: Chilled water flow rate (kg/s)
        m_dot_cw: Condenser water flow rate (kg/s)
        T_evap: Evaporator saturation temperature (°C)
        T_cond: Condenser saturation temperature (°C)
    """

    def __init__(self, rated_capacity_mw, rated_cop, t_chw_supply,
                 refrigerant='R134a', eta_is_comp=0.80,
                 evap_effectiveness=0.85, cond_effectiveness=0.85,
                 curves_file=None):
        """
        Initialize chiller module with full thermodynamic cycle modeling.

        Args:
            rated_capacity_mw: Rated cooling capacity (MW)
            rated_cop: COP at rated conditions (for validation)
            t_chw_supply: Chilled water supply temperature (°C)
            refrigerant: Refrigerant type (default 'R134a')
            eta_is_comp: Compressor isentropic efficiency (0-1)
            evap_effectiveness: Evaporator heat exchanger effectiveness (0-1)
            cond_effectiveness: Condenser heat exchanger effectiveness (0-1)
            curves_file: Deprecated (kept for backward compatibility)

        Raises:
            ValueError: If parameters are invalid
            ImportError: If CoolProp is not available
        """
        if not COOLPROP_AVAILABLE:
            raise ImportError("CoolProp is required for refrigeration cycle modeling. "
                            "Install with: pip install CoolProp")

        if rated_capacity_mw <= 0:
            raise ValueError(f"Invalid rated_capacity_mw: {rated_capacity_mw}, must be > 0")
        if rated_cop <= 0 or rated_cop > 10:
            raise ValueError(f"Invalid rated_cop: {rated_cop}, must be between 0 and 10")
        if t_chw_supply < 0 or t_chw_supply >= 30:
            raise ValueError(f"Invalid t_chw_supply: {t_chw_supply}, must be between 0 and 30 °C")

        self.rated_capacity = rated_capacity_mw * 1e6  # W
        self.rated_cop = rated_cop
        self.t_chw_supply = t_chw_supply
        self.cp_water = 4186  # J/(kg·K)

        # Refrigeration cycle components
        self.refrigerant = refrigerant
        self.ref_cycle = VaporCompressionCycle(
            refrigerant=refrigerant,
            eta_is_comp=eta_is_comp,
            superheat_evap=5.0,  # 5°C superheat at evaporator outlet
            subcool_cond=3.0      # 3°C subcooling at condenser outlet
        )

        # Heat exchangers
        self.evap_hx = HeatExchanger(effectiveness=evap_effectiveness)
        self.cond_hx = HeatExchanger(effectiveness=cond_effectiveness)

        # Approximate specific heats for refrigerant (will be refined in calculations)
        self.cp_ref_liquid = 1400  # J/(kg·K), approximate for R134a liquid
        self.cp_ref_vapor = 1200   # J/(kg·K), approximate for R134a vapor

    def solve_energy_balance(self, q_evap, m_dot_chw, m_dot_cw, t_cw_in, t_chw_return=None, max_iter=20, tolerance=0.1):
        """
        Solve complete chiller energy balance using refrigeration cycle and HX models.

        Iterative solution procedure:
        1. Estimate evaporator and condenser temperatures
        2. Solve refrigeration cycle for refrigerant states
        3. Solve evaporator HX: match refrigerant-side and water-side energy
        4. Solve condenser HX: match refrigerant-side and water-side energy
        5. Update evaporator/condenser temperatures
        6. Check convergence
        7. Repeat until converged

        Args:
            q_evap: Required evaporator cooling capacity (W)
            m_dot_chw: Chilled water flow rate (kg/s)
            m_dot_cw: Condenser water flow rate (kg/s)
            t_cw_in: Condenser water inlet temperature (°C)
            t_chw_return: Chilled water return temperature (°C), if None calculated from Q
            max_iter: Maximum iterations for convergence
            tolerance: Convergence tolerance for temperatures (°C)

        Returns:
            dict: Complete thermodynamic state information

        Raises:
            ValueError: If parameters are invalid or solution doesn't converge
        """
        if q_evap <= 0:
            raise ValueError(f"Invalid q_evap: {q_evap}, must be > 0")
        if m_dot_chw <= 0:
            raise ValueError(f"Invalid m_dot_chw: {m_dot_chw}, must be > 0")
        if m_dot_cw <= 0:
            raise ValueError(f"Invalid m_dot_cw: {m_dot_cw}, must be > 0")

        # Calculate chilled water return temperature if not provided
        if t_chw_return is None:
            delta_t_chw = q_evap / (m_dot_chw * self.cp_water)
            t_chw_return = self.t_chw_supply + delta_t_chw

        # Initial guess for evaporator and condenser temperatures
        # Evaporator sat temp ~5°C below CHW supply to allow heat transfer
        T_evap = self.t_chw_supply - 5.0
        # Condenser sat temp ~5°C above CW inlet to allow heat transfer
        T_cond = t_cw_in + 5.0

        # Iterative solution
        for iteration in range(max_iter):
            T_evap_old = T_evap
            T_cond_old = T_cond

            # Step 1: Solve refrigeration cycle
            try:
                cycle_result = self.ref_cycle.solve(
                    T_evap_C=T_evap,
                    T_cond_C=T_cond,
                    Q_evap_required=q_evap
                )
            except Exception as e:
                raise ValueError(f"Refrigeration cycle solution failed at iteration {iteration}: {e}")

            m_dot_ref = cycle_result['m_dot_ref_kg_s']
            q_cond_ref = cycle_result['Q_cond_W']
            w_comp = cycle_result['W_comp_W']

            # Step 2: Solve evaporator heat exchanger
            # Water side: hot fluid (being cooled from t_chw_return to t_chw_supply)
            # Refrigerant side: cold fluid (evaporating at T_evap, then superheating)
            T_ref_evap_out = self.ref_cycle.state1.T_C  # Superheated vapor out

            # Use HX model to verify temperature match
            # For evaporator, we target the required Q_evap
            evap_hx_result = self.evap_hx.solve_counterflow(
                m_dot_hot=m_dot_chw,
                cp_hot=self.cp_water,
                T_hot_in=t_chw_return,
                m_dot_cold=m_dot_ref,
                cp_cold=self.cp_ref_liquid,  # Approximate, two-phase
                T_cold_in=T_evap,
                Q_target=q_evap
            )

            # Update T_evap based on pinch point
            # Evaporator sat temp should be below CHW supply by at least pinch
            pinch_evap = t_chw_return - T_ref_evap_out
            if pinch_evap < 2.0:  # Minimum pinch
                T_evap -= 0.5  # Decrease evap temp to increase pinch
            elif pinch_evap > 8.0:  # Too much pinch
                T_evap += 0.3  # Increase evap temp

            # Step 3: Solve condenser heat exchanger
            # Refrigerant side: hot fluid (desuperheating, condensing, subcooling)
            # Water side: cold fluid (being heated from t_cw_in)
            T_ref_cond_in = self.ref_cycle.state2.T_C  # Superheated vapor in
            T_ref_cond_out = self.ref_cycle.state3.T_C  # Subcooled liquid out

            cond_hx_result = self.cond_hx.solve_counterflow(
                m_dot_hot=m_dot_ref,
                cp_hot=self.cp_ref_vapor,  # Approximate, two-phase
                T_hot_in=T_ref_cond_in,
                m_dot_cold=m_dot_cw,
                cp_cold=self.cp_water,
                T_cold_in=t_cw_in,
                Q_target=q_cond_ref
            )

            t_cw_out = cond_hx_result['T_cold_out_C']

            # Update T_cond based on pinch point
            pinch_cond = T_ref_cond_out - t_cw_out
            if pinch_cond < 2.0:  # Minimum pinch
                T_cond += 0.5  # Increase cond temp to increase pinch
            elif pinch_cond > 8.0:  # Too much pinch
                T_cond -= 0.3  # Decrease cond temp

            # Check convergence
            delta_T_evap = abs(T_evap - T_evap_old)
            delta_T_cond = abs(T_cond - T_cond_old)

            if delta_T_evap < tolerance and delta_T_cond < tolerance:
                # Converged
                cop = cycle_result['COP']
                plr = q_evap / self.rated_capacity

                return {
                    'component': 'Chiller (Thermodynamic Cycle)',
                    'refrigerant': self.refrigerant,
                    'converged': True,
                    'iterations': iteration + 1,

                    # Performance
                    'Q_evap_MW': q_evap / 1e6,
                    'Q_cond_MW': q_cond_ref / 1e6,
                    'W_comp_MW': w_comp / 1e6,
                    'COP': cop,
                    'PLR': plr,

                    # Chilled water side
                    'T_chw_supply_C': self.t_chw_supply,
                    'T_chw_return_C': t_chw_return,
                    'delta_T_chw_C': t_chw_return - self.t_chw_supply,
                    'm_dot_chw_kg_s': m_dot_chw,

                    # Condenser water side
                    'T_cw_in_C': t_cw_in,
                    'T_cw_out_C': t_cw_out,
                    'delta_T_cw_C': t_cw_out - t_cw_in,
                    'm_dot_cw_kg_s': m_dot_cw,

                    # Refrigerant side
                    'T_evap_sat_C': T_evap,
                    'T_cond_sat_C': T_cond,
                    'm_dot_ref_kg_s': m_dot_ref,
                    'P_evap_kPa': cycle_result['P_evap_Pa'] / 1000,
                    'P_cond_kPa': cycle_result['P_cond_Pa'] / 1000,
                    'compression_ratio': cycle_result['compression_ratio'],

                    # Energy balance check
                    'energy_balance_error_pct': abs(q_cond_ref - (q_evap + w_comp)) / q_cond_ref * 100,

                    # Heat exchanger effectiveness
                    'evap_effectiveness': evap_hx_result['effectiveness'],
                    'cond_effectiveness': cond_hx_result['effectiveness']
                }

        # Did not converge
        raise ValueError(f"Chiller solution did not converge after {max_iter} iterations. "
                       f"Last changes: ΔT_evap={delta_T_evap:.3f}°C, ΔT_cond={delta_T_cond:.3f}°C")


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
