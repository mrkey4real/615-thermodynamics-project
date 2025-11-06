"""
Refrigerant Properties Module

Provides thermodynamic property calculations for refrigerants used in
vapor compression cycles. Uses CoolProp library for accurate property data.

Supports R134a (common in water-cooled chillers).
"""

try:
    from CoolProp.CoolProp import PropsSI

    COOLPROP_AVAILABLE = True
except ImportError:
    COOLPROP_AVAILABLE = False
    print("WARNING: CoolProp not available. Using simplified refrigerant properties.")


class RefrigerantState:
    """
    Represents a thermodynamic state of refrigerant.

    Uses two independent intensive properties to define the state.
    Common combinations:
    - P, T (pressure, temperature)
    - P, h (pressure, enthalpy)
    - P, Q (pressure, quality for two-phase)
    - T, Q (temperature, quality for two-phase)
    """

    def __init__(self, fluid="R134a", **kwargs):
        """
        Initialize refrigerant state from two independent properties.

        Args:
            fluid: Refrigerant type ('R134a', 'R410A', etc.)
            **kwargs: Two of the following:
                P: Pressure (Pa)
                T: Temperature (K)
                h: Specific enthalpy (J/kg)
                s: Specific entropy (J/kg-K)
                Q: Quality (0-1, for two-phase only)

        Raises:
            ValueError: If invalid combination of properties
        """
        self.fluid = fluid

        if not COOLPROP_AVAILABLE:
            raise ImportError(
                "CoolProp is required for refrigerant properties. Install with: pip install CoolProp"
            )

        # Count specified properties
        valid_props = ["P", "T", "h", "s", "Q"]
        specified = {k: v for k, v in kwargs.items() if k in valid_props and v is not None}

        if len(specified) != 2:
            raise ValueError(
                f"Exactly two properties required, got {len(specified)}: {list(specified.keys())}"
            )

        # Store the specified properties
        for key, value in specified.items():
            setattr(self, f"_{key}", value)

        # Calculate all properties using CoolProp
        self._calculate_properties(specified)

    def _calculate_properties(self, specified):
        """
        Calculate all thermodynamic properties from the two specified ones.

        Args:
            specified: Dictionary of specified properties
        """
        # Map our property names to CoolProp names
        prop_map = {
            "P": "P",  # Pressure
            "T": "T",  # Temperature
            "h": "H",  # Enthalpy (mass basis)
            "s": "S",  # Entropy (mass basis)
            "Q": "Q",  # Quality
        }

        # Get the two input properties in CoolProp format
        keys = list(specified.keys())
        input1_name = prop_map[keys[0]]
        input1_value = specified[keys[0]]
        input2_name = prop_map[keys[1]]
        input2_value = specified[keys[1]]

        # Calculate all properties
        try:
            self.P = PropsSI("P", input1_name, input1_value, input2_name, input2_value, self.fluid)
            self.T = PropsSI("T", input1_name, input1_value, input2_name, input2_value, self.fluid)
            self.h = PropsSI("H", input1_name, input1_value, input2_name, input2_value, self.fluid)
            self.s = PropsSI("S", input1_name, input1_value, input2_name, input2_value, self.fluid)
            self.rho = PropsSI(
                "D", input1_name, input1_value, input2_name, input2_value, self.fluid
            )

            # Quality (Q) is only defined in two-phase region
            try:
                self.Q = PropsSI(
                    "Q", input1_name, input1_value, input2_name, input2_value, self.fluid
                )
            except:
                self.Q = None  # Subcooled liquid or superheated vapor

            # Phase identification
            self.phase = self._identify_phase()

        except Exception as e:
            raise ValueError(f"Failed to calculate refrigerant properties: {e}")

    def _identify_phase(self):
        """
        Identify the phase of the refrigerant.

        Returns:
            str: 'subcooled_liquid', 'two_phase', 'superheated_vapor', 'supercritical'
        """
        if self.Q is not None and 0 <= self.Q <= 1:
            return "two_phase"

        # Get critical pressure
        P_crit = PropsSI("PCRIT", self.fluid)

        if self.P > P_crit:
            return "supercritical"

        # Get saturation temperature at this pressure
        try:
            T_sat = PropsSI("T", "P", self.P, "Q", 0, self.fluid)

            if self.T < T_sat - 0.1:  # 0.1 K tolerance
                return "subcooled_liquid"
            elif self.T > T_sat + 0.1:
                return "superheated_vapor"
            else:
                return "saturated"
        except:
            # If we can't determine, use enthalpy
            h_sat_liq = PropsSI("H", "P", self.P, "Q", 0, self.fluid)
            h_sat_vap = PropsSI("H", "P", self.P, "Q", 1, self.fluid)

            if self.h < h_sat_liq:
                return "subcooled_liquid"
            elif self.h > h_sat_vap:
                return "superheated_vapor"
            else:
                return "two_phase"

    def to_celsius(self):
        """Return temperature in Celsius."""
        return self.T - 273.15

    def to_bar(self):
        """Return pressure in bar."""
        return self.P / 1e5

    def to_kJ_per_kg(self):
        """Return enthalpy in kJ/kg."""
        return self.h / 1e3

    def __repr__(self):
        """String representation of refrigerant state."""
        T_C = self.to_celsius()
        P_bar = self.to_bar()
        h_kJ = self.to_kJ_per_kg()

        if self.Q is not None:
            return (
                f"RefrigerantState({self.fluid}, {self.phase}, "
                f"P={P_bar:.2f} bar, T={T_C:.1f}°C, h={h_kJ:.1f} kJ/kg, Q={self.Q:.3f})"
            )
        else:
            return (
                f"RefrigerantState({self.fluid}, {self.phase}, "
                f"P={P_bar:.2f} bar, T={T_C:.1f}°C, h={h_kJ:.1f} kJ/kg)"
            )


class RefrigerantCycle:
    """
    Helper class for vapor compression refrigeration cycle calculations.

    Provides methods for common cycle processes:
    - Isentropic compression
    - Isenthalpic expansion
    - Evaporation and condensation at constant pressure
    """

    def __init__(self, fluid="R134a"):
        """
        Initialize refrigerant cycle helper.

        Args:
            fluid: Refrigerant type
        """
        self.fluid = fluid

        if not COOLPROP_AVAILABLE:
            raise ImportError("CoolProp is required for refrigerant cycle calculations")

    def isentropic_compression(self, state_in, P_out):
        """
        Calculate isentropic compression from inlet state to outlet pressure.

        Args:
            state_in: RefrigerantState at compressor inlet
            P_out: Outlet pressure (Pa)

        Returns:
            state_out_s: RefrigerantState at compressor outlet (isentropic)
        """
        # Isentropic: s_out = s_in
        return RefrigerantState(fluid=self.fluid, P=P_out, s=state_in.s)

    def actual_compression(self, state_in, P_out, eta_isentropic):
        """
        Calculate actual compression accounting for isentropic efficiency.

        W_actual = W_isentropic / eta_isentropic
        h_out_actual = h_in + (h_out_s - h_in) / eta

        Args:
            state_in: RefrigerantState at compressor inlet
            P_out: Outlet pressure (Pa)
            eta_isentropic: Isentropic efficiency (0-1)

        Returns:
            state_out: Actual RefrigerantState at compressor outlet
            w_comp: Specific work of compression (J/kg)
        """
        if not 0.0 < eta_isentropic <= 1.0:
            raise ValueError(f"Isentropic efficiency must be in (0,1], got {eta_isentropic}")

        # Isentropic outlet state
        state_out_s = self.isentropic_compression(state_in, P_out)

        # Actual outlet enthalpy
        h_out_actual = state_in.h + (state_out_s.h - state_in.h) / eta_isentropic

        # Actual outlet state
        state_out = RefrigerantState(fluid=self.fluid, P=P_out, h=h_out_actual)

        # Specific work
        w_comp = h_out_actual - state_in.h

        return state_out, w_comp

    def isenthalpic_expansion(self, state_in, P_out):
        """
        Calculate isenthalpic expansion (throttling) through expansion valve.

        Args:
            state_in: RefrigerantState at valve inlet (high pressure liquid)
            P_out: Outlet pressure (Pa)

        Returns:
            state_out: RefrigerantState at valve outlet (low pressure two-phase)
        """
        # Isenthalpic: h_out = h_in
        return RefrigerantState(fluid=self.fluid, P=P_out, h=state_in.h)

    def saturation_temperature(self, P):
        """
        Get saturation temperature at given pressure.

        Args:
            P: Pressure (Pa)

        Returns:
            T_sat: Saturation temperature (K)
        """
        return PropsSI("T", "P", P, "Q", 0, self.fluid)

    def saturation_pressure(self, T):
        """
        Get saturation pressure at given temperature.

        Args:
            T: Temperature (K)

        Returns:
            P_sat: Saturation pressure (Pa)
        """
        return PropsSI("P", "T", T, "Q", 0, self.fluid)


def test_refrigerant_properties():
    """
    Test refrigerant property calculations with R134a cycle.
    """
    if not COOLPROP_AVAILABLE:
        print("CoolProp not available. Skipping refrigerant tests.")
        return

    print("\n" + "=" * 70)
    print("REFRIGERANT PROPERTIES TEST - R134a VAPOR COMPRESSION CYCLE")
    print("=" * 70)

    cycle = RefrigerantCycle("R134a")

    # Define cycle conditions
    T_evap_C = 5.0  # Evaporator temperature (°C)
    T_cond_C = 40.0  # Condenser temperature (°C)
    subcool_C = 5.0  # Subcooling (°C)
    superheat_C = 5.0  # Superheat (°C)
    eta_comp = 0.85  # Compressor isentropic efficiency

    print("\nCycle Conditions:")
    print(f"  Evaporator temperature: {T_evap_C}°C")
    print(f"  Condenser temperature: {T_cond_C}°C")
    print(f"  Subcooling: {subcool_C}°C")
    print(f"  Superheat: {superheat_C}°C")
    print(f"  Compressor efficiency: {eta_comp*100:.1f}%")

    # State 1: Compressor inlet (superheated vapor)
    T1_K = (T_evap_C + superheat_C) + 273.15
    P1 = cycle.saturation_pressure(T_evap_C + 273.15)
    state1 = RefrigerantState("R134a", P=P1, T=T1_K)
    print("\nState 1 (Compressor Inlet - Superheated Vapor):")
    print(f"  {state1}")

    # State 2: Compressor outlet (superheated vapor, high pressure)
    P2 = cycle.saturation_pressure(T_cond_C + 273.15)
    state2, w_comp = cycle.actual_compression(state1, P2, eta_comp)
    print("\nState 2 (Compressor Outlet - Superheated Vapor):")
    print(f"  {state2}")
    print(f"  Specific work: {w_comp/1e3:.1f} kJ/kg")

    # State 3: Condenser outlet (subcooled liquid)
    T3_K = (T_cond_C - subcool_C) + 273.15
    state3 = RefrigerantState("R134a", P=P2, T=T3_K)
    print("\nState 3 (Condenser Outlet - Subcooled Liquid):")
    print(f"  {state3}")

    # State 4: Expansion valve outlet (two-phase, low pressure)
    state4 = cycle.isenthalpic_expansion(state3, P1)
    print("\nState 4 (Expansion Valve Outlet - Two-Phase):")
    print(f"  {state4}")

    # Calculate cycle performance
    q_evap = state1.h - state4.h  # Cooling effect (J/kg)
    q_cond = state2.h - state3.h  # Heat rejection (J/kg)
    COP = q_evap / w_comp

    print("\nCycle Performance:")
    print(f"  Cooling effect (q_evap): {q_evap/1e3:.1f} kJ/kg")
    print(f"  Heat rejection (q_cond): {q_cond/1e3:.1f} kJ/kg")
    print(f"  Compressor work: {w_comp/1e3:.1f} kJ/kg")
    print(f"  COP: {COP:.2f}")
    print(
        f"  Energy balance check: q_evap + w = {(q_evap+w_comp)/1e3:.1f} kJ/kg, q_cond = {q_cond/1e3:.1f} kJ/kg"
    )
    print(f"  Balance error: {abs(q_evap+w_comp-q_cond)/q_cond*100:.4f}%")

    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    test_refrigerant_properties()
