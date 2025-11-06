"""
Building Load Module

Models air-cooled equipment thermal load.
Energy Balance: Q = m_dot_air * cp_air * delta_T
"""


class BuildingLoad:
    """
    Models air-cooled equipment thermal load.

    Energy Balance:
        Q = m_dot_air * cp_air * delta_T

    Variables:
        Q_building: Building equipment heat load (W)
        m_dot_air: Air mass flow rate (kg/s)
        T_air_in: Inlet air temperature (C)
        T_air_out: Outlet air temperature (C)
        cp_air: Specific heat of air (J/kg-K)
    """

    def __init__(self, aircool_load_mw, max_temp):
        """
        Initialize building load module.

        Args:
            aircool_load_mw: Air-cooled equipment load (MW)
            max_temp: Maximum air temperature for human comfort (C)

        Raises:
            ValueError: If parameters are invalid
        """
        if aircool_load_mw <= 0:
            raise ValueError(f"Invalid aircool_load_mw: {aircool_load_mw}, must be > 0")
        if max_temp <= 0 or max_temp >= 50:
            raise ValueError(f"Invalid max_temp: {max_temp}, must be between 0 and 50 C")

        self.aircool_load = aircool_load_mw * 1e6  # Convert to W
        self.max_temp = max_temp
        self.cp_air = 1005  # J/(kg-K) at ~20 C

    def calculate_heat_load(self, utilization=1.0):
        """
        Calculate actual heat load.

        Args:
            utilization: Equipment utilization factor (0-1)

        Returns:
            Q_actual: Heat load (W)

        Raises:
            ValueError: If utilization is out of range
        """
        if not 0.0 <= utilization <= 1.0:
            raise ValueError(f"Invalid utilization: {utilization}, must be between 0 and 1")

        return self.aircool_load * utilization

    def calculate_outlet_temp(self, T_air_in, m_dot_air):
        """
        Calculate outlet air temperature.

        Energy Balance: Q = m_dot * cp * (T_out - T_in)
        Solve for: T_out = T_in + Q / (m_dot * cp)

        Args:
            T_air_in: Inlet air temperature (C)
            m_dot_air: Air mass flow rate (kg/s)

        Returns:
            T_air_out: Outlet air temperature (C)

        Raises:
            ValueError: If parameters are invalid
        """
        if m_dot_air <= 0:
            raise ValueError(f"Invalid m_dot_air: {m_dot_air}, must be > 0")
        if T_air_in < 0 or T_air_in >= 50:
            raise ValueError(f"Invalid T_air_in: {T_air_in}, must be between 0 and 50 C")

        Q = self.calculate_heat_load()
        delta_T = Q / (m_dot_air * self.cp_air)
        T_air_out = T_air_in + delta_T
        return T_air_out

    def check_temperature_constraint(self, T_air_out):
        """
        Verify air temperature constraint for human comfort.

        Constraint: T_air_out <= max_temp (typically 25 C)

        Args:
            T_air_out: Outlet air temperature (C)

        Returns:
            bool: True if constraint satisfied
        """
        return T_air_out <= self.max_temp

    def calculate_required_flow_rate(self, T_air_in, T_air_out_target=None):
        """
        Calculate minimum air flow rate.

        Args:
            T_air_in: Inlet air temperature (C)
            T_air_out_target: Target outlet temperature (C), defaults to max_temp

        Returns:
            m_dot_air_min: Minimum air mass flow rate (kg/s)

        Raises:
            ValueError: If parameters are invalid
        """
        if T_air_out_target is None:
            T_air_out_target = self.max_temp

        if T_air_out_target <= T_air_in:
            raise ValueError(f"T_air_out_target ({T_air_out_target}) must be > T_air_in ({T_air_in})")

        Q = self.calculate_heat_load()
        delta_T_max = T_air_out_target - T_air_in
        m_dot_air_min = Q / (self.cp_air * delta_T_max)
        return m_dot_air_min

    def get_state_summary(self, T_air_in, m_dot_air):
        """
        Return complete state information.

        Args:
            T_air_in: Inlet air temperature (C)
            m_dot_air: Air mass flow rate (kg/s)

        Returns:
            dict: State variables and energy balance
        """
        Q = self.calculate_heat_load()
        T_air_out = self.calculate_outlet_temp(T_air_in, m_dot_air)
        constraint_ok = self.check_temperature_constraint(T_air_out)

        return {
            'component': 'Building Load',
            'Q_load_MW': Q / 1e6,
            'm_dot_air_kg_s': m_dot_air,
            'T_air_in_C': T_air_in,
            'T_air_out_C': T_air_out,
            'delta_T_C': T_air_out - T_air_in,
            'max_temp_C': self.max_temp,
            'constraint_satisfied': constraint_ok
        }
