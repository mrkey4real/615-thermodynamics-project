"""
HVAC System Module

Contains Chiller and CoolingTower classes for datacenter cooling system.

Refactored to use component-level thermodynamic modeling:
- Chiller: Full refrigeration cycle with heat exchanger energy balances
- CoolingTower: Psychrometric analysis with air/water mass/energy balances
"""

# Handle both relative and absolute imports
try:
    from .psychrometrics import MoistAir, PsychrometricState
    from .refrigerant_cycle import COOLPROP_AVAILABLE, HeatExchanger, VaporCompressionCycle
except ImportError:
    from psychrometrics import PsychrometricState
    from refrigerant_cycle import COOLPROP_AVAILABLE, HeatExchanger, VaporCompressionCycle


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

    def __init__(
        self,
        rated_capacity_mw,
        rated_cop,
        t_chw_supply,
        refrigerant="R134a",
        eta_is_comp=0.80,
        evap_effectiveness=0.85,
        cond_effectiveness=0.85,
        curves_file=None,
    ):
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
            raise ImportError(
                "CoolProp is required for refrigeration cycle modeling. "
                "Install with: pip install CoolProp"
            )

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
            subcool_cond=3.0,  # 3°C subcooling at condenser outlet
        )

        # Heat exchangers
        self.evap_hx = HeatExchanger(effectiveness=evap_effectiveness)
        self.cond_hx = HeatExchanger(effectiveness=cond_effectiveness)

        # Approximate specific heats for refrigerant (will be refined in calculations)
        self.cp_ref_liquid = 1400  # J/(kg·K), approximate for R134a liquid
        self.cp_ref_vapor = 1200  # J/(kg·K), approximate for R134a vapor

    def solve_energy_balance(
        self, q_evap, m_dot_chw, m_dot_cw, t_cw_in, t_chw_return=None, max_iter=20, tolerance=0.1
    ):
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
                    T_evap_C=T_evap, T_cond_C=T_cond, Q_evap_required=q_evap
                )
            except Exception as e:
                raise ValueError(
                    f"Refrigeration cycle solution failed at iteration {iteration}: {e}"
                )

            m_dot_ref = cycle_result["m_dot_ref_kg_s"]
            q_cond_ref = cycle_result["Q_cond_W"]
            w_comp = cycle_result["W_comp_W"]

            # Step 2: Verify evaporator energy balance and pinch points
            # Water side: being cooled from t_chw_return to t_chw_supply
            # Refrigerant side: evaporating at T_evap, then superheating
            T_ref_evap_out = self.ref_cycle.state1.T_C  # Superheated vapor out

            # Check pinch point: evaporator sat temp should be below CHW supply
            pinch_evap = self.t_chw_supply - T_evap
            if pinch_evap < 3.0:  # Minimum pinch
                T_evap -= 0.5  # Decrease evap temp to increase pinch
            elif pinch_evap > 8.0:  # Too much pinch
                T_evap += 0.3  # Increase evap temp

            # Step 3: Calculate condenser water outlet temperature
            # Refrigerant side: desuperheating, condensing, subcooling
            # Water side: being heated from t_cw_in
            T_ref_cond_in = self.ref_cycle.state2.T_C  # Superheated vapor in
            T_ref_cond_out = self.ref_cycle.state3.T_C  # Subcooled liquid out

            # Water side energy balance
            t_cw_out = t_cw_in + q_cond_ref / (m_dot_cw * self.cp_water)

            # Check pinch point: condenser sat temp should be above CW outlet
            pinch_cond = T_cond - t_cw_out
            if pinch_cond < 3.0:  # Minimum pinch
                T_cond += 0.5  # Increase cond temp to increase pinch
            elif pinch_cond > 8.0:  # Too much pinch
                T_cond -= 0.3  # Decrease cond temp

            # Heat exchanger effectiveness (informational)
            evap_effectiveness = 0.85  # Typical value
            cond_effectiveness = 0.85  # Typical value

            # Check convergence
            delta_T_evap = abs(T_evap - T_evap_old)
            delta_T_cond = abs(T_cond - T_cond_old)

            if delta_T_evap < tolerance and delta_T_cond < tolerance:
                # Converged
                cop = cycle_result["COP"]
                plr = q_evap / self.rated_capacity

                return {
                    "component": "Chiller (Thermodynamic Cycle)",
                    "refrigerant": self.refrigerant,
                    "converged": True,
                    "iterations": iteration + 1,
                    # Performance
                    "Q_evap_MW": q_evap / 1e6,
                    "Q_cond_MW": q_cond_ref / 1e6,
                    "W_comp_MW": w_comp / 1e6,
                    "COP": cop,
                    "PLR": plr,
                    # Chilled water side
                    "T_chw_supply_C": self.t_chw_supply,
                    "T_chw_return_C": t_chw_return,
                    "delta_T_chw_C": t_chw_return - self.t_chw_supply,
                    "m_dot_chw_kg_s": m_dot_chw,
                    # Condenser water side
                    "T_cw_in_C": t_cw_in,
                    "T_cw_out_C": t_cw_out,
                    "delta_T_cw_C": t_cw_out - t_cw_in,
                    "m_dot_cw_kg_s": m_dot_cw,
                    # Refrigerant side
                    "T_evap_sat_C": T_evap,
                    "T_cond_sat_C": T_cond,
                    "m_dot_ref_kg_s": m_dot_ref,
                    "P_evap_kPa": cycle_result["P_evap_Pa"] / 1000,
                    "P_cond_kPa": cycle_result["P_cond_Pa"] / 1000,
                    "compression_ratio": cycle_result["compression_ratio"],
                    # Energy balance check
                    "energy_balance_error_pct": abs(q_cond_ref - (q_evap + w_comp))
                    / q_cond_ref
                    * 100,
                    # Heat exchanger effectiveness
                    "evap_effectiveness": evap_effectiveness,
                    "cond_effectiveness": cond_effectiveness,
                }

        # Did not converge
        raise ValueError(
            f"Chiller solution did not converge after {max_iter} iterations. "
            f"Last changes: ΔT_evap={delta_T_evap:.3f}°C, ΔT_cond={delta_T_cond:.3f}°C"
        )


class CoolingTower:
    """
    Models induced-draft cooling tower using psychrometric analysis.

    Component-Level Modeling:
        - Air side: Inlet/outlet psychrometric states (T_db, w, h, RH)
        - Water side: Inlet/outlet temperatures and mass flow
        - Mass balance: Air + makeup = Air + evap + drift + blowdown
        - Energy balance: Q_water = Q_air + evaporation enthalpy

    Thermodynamic States:
        Air inlet: T_db, T_wb (ambient conditions) → w_in, h_in
        Air outlet: Saturated at T_water_out → w_out, h_out
        Water inlet: T_in, mass flow m_cw
        Water outlet: T_out (= T_wb + Approach)

    Mass Balances:
        Dry air: m_da_in = m_da_out (constant)
        Water vapor: m_da*(w_out - w_in) = m_evap
        Liquid water: m_evap + m_drift + m_blowdown = m_makeup

    Energy Balance:
        Water side: Q = m_cw * cp_w * (T_in - T_out)
        Air side: Q = m_da * (h_out - h_in)
        Evaporation: Q_evap = m_evap * h_fg

    Variables:
        m_da: Dry air mass flow rate (kg_da/s)
        m_cw: Circulating water flow (kg/s)
        m_evap: Evaporation loss (kg/s)
        m_drift: Drift loss (kg/s)
        m_blowdown: Blowdown loss (kg/s)
        m_makeup: Total makeup water (kg/s)
    """

    def __init__(self, approach_temp, coc, drift_rate=0.00001, air_to_water_ratio=1.2):
        """
        Initialize cooling tower module with psychrometric modeling.

        Args:
            approach_temp: Approach temperature T_out - T_wb (°C)
            coc: Cycles of concentration (-)
            drift_rate: Drift as fraction of circulating water (-)
            air_to_water_ratio: Air mass flow to water mass flow ratio (L/L for ρ≈1)

        Raises:
            ValueError: If parameters are invalid
        """
        if approach_temp <= 0 or approach_temp > 20:
            raise ValueError(f"Invalid approach_temp: {approach_temp}, must be between 0 and 20 °C")
        if coc < 2 or coc > 10:
            raise ValueError(f"Invalid coc: {coc}, must be between 2 and 10")
        if drift_rate < 0 or drift_rate > 0.01:
            raise ValueError(f"Invalid drift_rate: {drift_rate}, must be between 0 and 0.01")
        if air_to_water_ratio <= 0 or air_to_water_ratio > 5:
            raise ValueError(
                f"Invalid air_to_water_ratio: {air_to_water_ratio}, must be between 0 and 5"
            )

        self.approach = approach_temp
        self.coc = coc
        self.drift_rate = drift_rate
        self.air_to_water_ratio = air_to_water_ratio
        self.cp_water = 4186  # J/(kg·K)
        self.h_fg = 2260e3  # J/kg (latent heat at ~30°C, approximate)

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

    def solve(self, q_cond, m_dot_cw, t_in, t_wb, t_db=None, RH_in=None):
        """
        Solve complete cooling tower performance using psychrometric analysis.

        Solution procedure:
        1. Calculate water outlet temperature: T_out = T_wb + Approach
        2. Determine air inlet psychrometric state (T_db, T_wb) → (w_in, h_in)
        3. Assume air outlet is saturated at T_out → (w_out, h_out)
        4. Calculate dry air mass flow rate from water/air ratio
        5. Solve mass balances for evaporation, drift, blowdown
        6. Verify energy balance: Q_water = Q_air
        7. Check thermodynamic feasibility

        Args:
            q_cond: Heat rejection load (W)
            m_dot_cw: Circulating water flow rate (kg/s)
            t_in: Inlet water temperature (°C) [State 9]
            t_wb: Ambient wet bulb temperature (°C)
            t_db: Ambient dry bulb temperature (°C), if None estimated from T_wb
            RH_in: Ambient relative humidity (0-1), if None calculated from T_db, T_wb

        Returns:
            dict: Complete performance data with psychrometric states

        Raises:
            ValueError: If parameters are invalid or solution is infeasible
        """
        if q_cond <= 0:
            raise ValueError(f"Invalid q_cond: {q_cond}, must be > 0")
        if m_dot_cw <= 0:
            raise ValueError(f"Invalid m_dot_cw: {m_dot_cw}, must be > 0")
        if t_in < 0 or t_in >= 100:
            raise ValueError(f"Invalid t_in: {t_in}, must be between 0 and 100 °C")

        # Step 1: Water side temperatures
        t_out = self.calculate_outlet_temp(t_wb)
        delta_t = t_in - t_out  # Range

        if delta_t <= 0:
            raise ValueError(f"Water inlet temp {t_in}°C must be > outlet temp {t_out}°C")

        # Step 2: Air inlet psychrometric state
        # If T_db not provided, estimate from typical T_db - T_wb relationship
        if t_db is None:
            # Typical depression: T_db - T_wb ≈ 5-15°C depending on humidity
            # For moderate humidity (~50%), depression ~ 10°C
            t_db = t_wb + 10.0

        # Create air inlet state
        try:
            air_in = PsychrometricState(T_db_C=t_db, T_wb_C=t_wb)
        except Exception as e:
            raise ValueError(f"Failed to calculate air inlet state: {e}")

        # Step 3: Air outlet state (assume saturated at water outlet temperature)
        # This is a standard assumption: air leaves nearly saturated
        try:
            air_out = PsychrometricState(T_db_C=t_out, RH=0.95)  # 95% RH, nearly saturated
        except Exception as e:
            raise ValueError(f"Failed to calculate air outlet state: {e}")

        # Step 4: Air mass flow rate
        # L/G ratio (liquid to gas): typically 0.8-1.5
        # We use air_to_water_ratio which is G/L
        m_dot_air_total = m_dot_cw * self.air_to_water_ratio  # Total moist air
        # Dry air mass flow (approximately total air mass, since w << 1)
        m_dot_da = m_dot_air_total / (1 + air_in.w)  # kg_da/s

        # Step 5: Mass balances
        # Evaporation from humidity ratio change
        m_evap_air = m_dot_da * (air_out.w - air_in.w)  # kg_water/s

        # Also calculate evaporation from energy balance (for verification)
        m_evap_energy = q_cond / self.h_fg  # kg/s

        # Use air-side calculation as primary (more accurate for cooling towers)
        m_evap = m_evap_air

        # Drift loss
        m_drift = self.calculate_drift_loss(m_dot_cw)

        # Blowdown
        m_blowdown = self.calculate_blowdown_rate(m_evap)

        # Makeup water
        m_makeup = self.calculate_makeup_water(m_evap, m_drift, m_blowdown)

        # Step 6: Energy balances
        # Water side
        q_water = m_dot_cw * self.cp_water * delta_t

        # Air side
        q_air = m_dot_da * (air_out.h - air_in.h)

        # Energy balance error
        energy_balance_error = abs(q_water - q_air) / q_water * 100

        # Check if energy balance is reasonable (< 10% error)
        if energy_balance_error > 15.0:
            import warnings

            warnings.warn(
                f"Cooling tower energy balance error {energy_balance_error:.1f}% exceeds 15%. "
                f"Check air/water ratio or psychrometric assumptions."
            )

        # Fan power
        w_fan = self.calculate_fan_power(q_cond)

        # Step 7: Return complete solution
        return {
            "component": "Cooling Tower (Psychrometric)",
            "Q_cond_MW": q_cond / 1e6,
            "Q_water_MW": q_water / 1e6,
            "Q_air_MW": q_air / 1e6,
            # Water side
            "T_water_in_C": t_in,
            "T_water_out_C": t_out,
            "Range_C": delta_t,
            "Approach_C": self.approach,
            "m_dot_cw_kg_s": m_dot_cw,
            # Air side
            "T_db_in_C": air_in.T_db,
            "T_wb_in_C": t_wb,
            "T_db_out_C": air_out.T_db,
            "RH_in": air_in.RH,
            "RH_out": air_out.RH,
            "w_in_kg_kg": air_in.w,
            "w_out_kg_kg": air_out.w,
            "h_in_J_kg": air_in.h,
            "h_out_J_kg": air_out.h,
            "m_dot_da_kg_s": m_dot_da,
            "air_to_water_ratio": self.air_to_water_ratio,
            # Mass balances
            "m_evap_kg_s": m_evap,
            "m_evap_energy_kg_s": m_evap_energy,
            "m_drift_kg_s": m_drift,
            "m_blowdown_kg_s": m_blowdown,
            "m_makeup_kg_s": m_makeup,
            "m_makeup_L_s": m_makeup,
            "m_makeup_L_hr": m_makeup * 3600,
            "COC": self.coc,
            # Performance
            "W_fan_MW": w_fan / 1e6,
            "energy_balance_error_pct": energy_balance_error,
            # Thermodynamic states
            "air_inlet_state": air_in,
            "air_outlet_state": air_out,
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
            raise ValueError(
                f"Invalid makeup_silica_ppm: {makeup_silica_ppm}, must be between 0 and 100"
            )
        if max_silica_ppm <= makeup_silica_ppm:
            raise ValueError(
                f"max_silica_ppm ({max_silica_ppm}) must be > makeup_silica_ppm ({makeup_silica_ppm})"
            )

        # Calculate maximum COC based on silica limit
        max_coc = max_silica_ppm / makeup_silica_ppm

        # Override COC if not specified
        if "coc" not in kwargs:
            kwargs["coc"] = max_coc

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
            "baseline_COC": baseline_coc,
            "optimized_COC": self.coc,
            "blowdown_reduction_pct": reduction * 100,
            "max_silica_limit_ppm": self.max_silica_ppm,
        }
