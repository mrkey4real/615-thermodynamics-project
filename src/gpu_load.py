"""
GPU Load Module

Models the thermal load from liquid-cooled GPU cluster.
Energy Balance: Q = m_dot * cp * delta_T
"""


class GPULoad:
    """
    Models the thermal load from liquid-cooled GPU cluster.

    Energy Balance:
        Q = m_dot * cp * delta_T

    Variables:
        Q_GPU: GPU heat load (W)
        m_dot_gpu: GPU coolant mass flow rate (kg/s)
        T_in: Inlet coolant temperature (C) [State 5]
        T_out: Outlet coolant temperature (C) [State 6]
        cp: Specific heat of coolant (J/kg-K)
    """

    def __init__(self, gpu_model, tdp_per_gpu, total_load_mw, max_temp):
        """
        Initialize GPU load module.

        Args:
            gpu_model: GPU identifier (str)
            tdp_per_gpu: Thermal design power per GPU (W)
            total_load_mw: Total GPU thermal load (MW)
            max_temp: Maximum allowable coolant temperature (C)

        Raises:
            ValueError: If parameters are invalid
        """
        if total_load_mw <= 0:
            raise ValueError(f"Invalid total_load_mw: {total_load_mw}, must be > 0")
        if tdp_per_gpu <= 0:
            raise ValueError(f"Invalid tdp_per_gpu: {tdp_per_gpu}, must be > 0")
        if max_temp <= 0 or max_temp >= 100:
            raise ValueError(f"Invalid max_temp: {max_temp}, must be between 0 and 100 C")

        self.gpu_model = gpu_model
        self.tdp = tdp_per_gpu  # W per GPU
        self.total_load = total_load_mw * 1e6  # Convert to W
        self.max_temp = max_temp
        self.num_gpus = int(self.total_load / self.tdp)
        self.cp_water = 4186  # J/(kg-K)

    def calculate_heat_load(self, utilization=1.0):
        """
        Calculate actual heat load based on utilization.

        Args:
            utilization: GPU utilization factor (0-1)

        Returns:
            Q_actual: Actual heat load (W)

        Raises:
            ValueError: If utilization is out of range
        """
        if not 0.0 <= utilization <= 1.0:
            raise ValueError(f"Invalid utilization: {utilization}, must be between 0 and 1")

        return self.total_load * utilization

    def calculate_outlet_temp(self, T_in, m_dot):
        """
        Calculate outlet coolant temperature from energy balance.

        Energy Balance: Q = m_dot * cp * (T_out - T_in)
        Solve for: T_out = T_in + Q / (m_dot * cp)

        Args:
            T_in: Inlet temperature (C) [State 5]
            m_dot: Mass flow rate (kg/s)

        Returns:
            T_out: Outlet temperature (C) [State 6]

        Raises:
            ValueError: If parameters are invalid
        """
        if m_dot <= 0:
            raise ValueError(f"Invalid m_dot: {m_dot}, must be > 0")
        if T_in < 0 or T_in >= 100:
            raise ValueError(f"Invalid T_in: {T_in}, must be between 0 and 100 C")

        Q = self.calculate_heat_load()
        delta_T = Q / (m_dot * self.cp_water)
        T_out = T_in + delta_T
        return T_out

    def check_temperature_constraint(self, T_out):
        """
        Verify outlet temperature meets constraint.

        Constraint: T_out <= max_temp (typically 40 C)

        Args:
            T_out: Outlet temperature (C)

        Returns:
            bool: True if constraint satisfied
        """
        return T_out <= self.max_temp

    def calculate_required_flow_rate(self, T_in, T_out_target=None):
        """
        Calculate minimum flow rate to meet temperature constraint.

        From energy balance:
            m_dot_min = Q / (cp * delta_T_max)

        Args:
            T_in: Inlet temperature (C)
            T_out_target: Target outlet temperature (C), defaults to max_temp

        Returns:
            m_dot_min: Minimum mass flow rate (kg/s)

        Raises:
            ValueError: If parameters are invalid
        """
        if T_out_target is None:
            T_out_target = self.max_temp

        if T_out_target <= T_in:
            raise ValueError(f"T_out_target ({T_out_target}) must be > T_in ({T_in})")

        Q = self.calculate_heat_load()
        delta_T_max = T_out_target - T_in
        m_dot_min = Q / (self.cp_water * delta_T_max)
        return m_dot_min

    def get_state_summary(self, T_in, m_dot):
        """
        Return complete state information.

        Args:
            T_in: Inlet temperature (C)
            m_dot: Mass flow rate (kg/s)

        Returns:
            dict: State variables and energy balance
        """
        Q = self.calculate_heat_load()
        T_out = self.calculate_outlet_temp(T_in, m_dot)
        constraint_ok = self.check_temperature_constraint(T_out)

        return {
            "component": "GPU Load",
            "gpu_model": self.gpu_model,
            "num_gpus": self.num_gpus,
            "Q_load_MW": Q / 1e6,
            "m_dot_kg_s": m_dot,
            "T_in_C": T_in,
            "T_out_C": T_out,
            "delta_T_C": T_out - T_in,
            "max_temp_C": self.max_temp,
            "constraint_satisfied": constraint_ok,
        }
