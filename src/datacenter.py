"""
DataCenter System Integration Module

Integrates all components into system-level model with energy balance calculations.
"""

from .gpu_load import GPULoad
from .building_load import BuildingLoad
from .hvac_system import Chiller, CoolingTower, CoolingTowerOptimized


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

    def __init__(self, config):
        """
        Initialize datacenter system.

        Args:
            config: Configuration dictionary with required keys

        Raises:
            ValueError: If configuration is missing required parameters
        """
        # Validate required configuration parameters
        required_params = [
            'gpu_load_mw', 'building_load_mw', 'chiller_rated_cop',
            'cooling_tower_approach', 'coc', 't_chw_supply',
            't_gpu_in', 't_air_in', 't_wb_ambient'
        ]

        for param in required_params:
            if param not in config:
                raise ValueError(f"Configuration missing required parameter: '{param}'")

        self.config = config

        # Initialize components
        self.gpu_load = GPULoad(
            gpu_model=config.get('gpu_model', 'NVIDIA B200'),
            tdp_per_gpu=config.get('tdp_per_gpu', 1200),
            total_load_mw=config['gpu_load_mw'],
            max_temp=config.get('gpu_max_temp', 40.0)
        )

        self.building_load = BuildingLoad(
            aircool_load_mw=config['building_load_mw'],
            max_temp=config.get('building_max_temp', 25.0)
        )

        self.chiller = Chiller(
            rated_capacity_mw=config.get('chiller_rated_capacity_mw', 1000),
            rated_cop=config['chiller_rated_cop'],
            t_chw_supply=config['t_chw_supply'],
            curves_file=config.get('chiller_curves_file', None)
        )

        # Use optimized cooling tower if requested
        if config.get('use_optimized_tower', False):
            self.cooling_tower = CoolingTowerOptimized(
                approach_temp=config['cooling_tower_approach'],
                coc=config['coc'],
                drift_rate=config.get('drift_rate', 0.00001),
                makeup_silica_ppm=config.get('makeup_silica_ppm', 25),
                max_silica_ppm=config.get('max_silica_ppm', 150)
            )
        else:
            self.cooling_tower = CoolingTower(
                approach_temp=config['cooling_tower_approach'],
                coc=config['coc'],
                drift_rate=config.get('drift_rate', 0.00001)
            )

        # Initialize state points
        self.state_points = self._initialize_state_points()

        # Calculate design flow rates
        self.flow_rates = self._calculate_design_flow_rates()

    def _initialize_state_points(self):
        """
        Initialize temperature state points with reasonable guesses.

        Returns:
            dict: Initial state point temperatures (C)
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
            'T10_cw_to_chiller': self.config['t_wb_ambient'] + self.config['cooling_tower_approach']
        }

    def _calculate_design_flow_rates(self):
        """
        Calculate design mass flow rates for all loops.

        Returns:
            dict: Flow rates (kg/s)
        """
        cp = 4186  # J/(kg-K)

        # GPU coolant loop
        # Q = m_dot * cp * delta_T, solve for m_dot
        q_gpu = self.config['gpu_load_mw'] * 1e6  # W
        delta_t_gpu = 25.0  # Conservative: 40 C - 15 C
        m_gpu = q_gpu / (cp * delta_t_gpu)

        # Chilled water loop
        q_evap = (self.config['gpu_load_mw'] + self.config['building_load_mw']) * 1e6
        delta_t_chw = 5.0  # Standard: 10 C supply, 15 C return
        m_chw = q_evap / (cp * delta_t_chw)

        # Condenser water loop (estimate)
        # Q_cond ≈ Q_evap * 1.15 (assuming COP~6)
        q_cond_estimate = q_evap * 1.15
        delta_t_cw = 5.5  # Typical range
        m_cw = q_cond_estimate / (cp * delta_t_cw)

        # Air flow rate for building
        cp_air = 1005  # J/(kg-K)
        q_building = self.config['building_load_mw'] * 1e6
        delta_t_air = 5.0  # Conservative: 25 C - 20 C
        m_air = q_building / (cp_air * delta_t_air)

        return {
            'm_gpu': m_gpu,
            'm_chw': m_chw,
            'm_cw': m_cw,
            'm_air': m_air
        }

    def solve_steady_state(self, utilization=1.0, t_wb=None, max_iter=100, tolerance=0.01):
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
            t_wb: Ambient wet bulb temperature (C)
            max_iter: Maximum iterations
            tolerance: Convergence tolerance (C)

        Returns:
            dict: Complete system solution

        Raises:
            ValueError: If parameters are invalid
        """
        if not 0.0 <= utilization <= 1.0:
            raise ValueError(f"Invalid utilization: {utilization}, must be between 0 and 1")

        if t_wb is None:
            t_wb = self.config['t_wb_ambient']

        if t_wb < -20 or t_wb > 50:
            raise ValueError(f"Invalid t_wb: {t_wb}, must be between -20 and 50 C")

        # Iteration loop
        converged = False
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
            t_cw_from_chiller = chiller_result['T_cw_out_C']
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

            # Building air temperature
            t_air_out = self.building_load.calculate_outlet_temp(
                T_air_in=self.config['t_air_in'],
                m_dot_air=self.flow_rates['m_air']
            )

            # Step 5: Check convergence
            max_change = max(
                abs(self.state_points[key] - state_old[key])
                for key in self.state_points
                if isinstance(self.state_points[key], (int, float))
            )

            if max_change < tolerance:
                converged = True
                break

        # Calculate auxiliary power consumption
        w_pumps = self._calculate_pump_power(q_evap)
        w_fans = tower_result['W_fan_MW'] * 1e6

        # Compile results
        results = {
            'converged': converged,
            'iterations': iteration + 1,
            'utilization': utilization,
            'T_wb_C': t_wb,
            'max_change_C': max_change if not converged else 0.0,

            # Power flows
            'P_IT_MW': (q_gpu + q_building) / 1e6,
            'Q_GPU_MW': q_gpu / 1e6,
            'Q_building_MW': q_building / 1e6,
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
            'm_drift_kg_s': tower_result['m_drift_kg_s'],
            'COC': tower_result['COC'],

            # State points
            'state_points': self.state_points.copy(),

            # Constraint checks
            'gpu_temp_ok': self.gpu_load.check_temperature_constraint(t_gpu_out),
            'building_temp_ok': self.building_load.check_temperature_constraint(t_air_out),
            'T_gpu_out_C': t_gpu_out,
            'T_air_out_C': t_air_out,

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

        Args:
            results: Results dictionary from solve_steady_state()
        """
        pue = self.calculate_pue(results)
        wue = self.calculate_wue(results)

        print("\n" + "="*70)
        print("DATACENTER COOLING SYSTEM - PERFORMANCE SUMMARY")
        print("="*70)

        print("\n--- IT LOAD ---")
        print(f"Total IT Load:        {results['P_IT_MW']:>8.1f} MW")
        print(f"GPU Load (90%):       {results['Q_GPU_MW']:>8.1f} MW")
        print(f"Building Load (10%):  {results['Q_building_MW']:>8.1f} MW")
        print(f"Number of GPUs:       {self.gpu_load.num_gpus:>8,}")
        print(f"Utilization:          {results['utilization']*100:>8.1f}%")

        print("\n--- COOLING SYSTEM POWER ---")
        print(f"Chiller Compressor:   {results['W_comp_MW']:>8.1f} MW")
        print(f"Pumps (all loops):    {results['W_pumps_MW']:>8.1f} MW")
        print(f"Cooling Tower Fans:   {results['W_fans_MW']:>8.1f} MW")
        print(f"Total Cooling:        {results['W_cooling_total_MW']:>8.1f} MW")

        print("\n--- PERFORMANCE METRICS ---")
        print(f"PUE:                  {pue:>8.3f}")
        print(f"Chiller COP:          {results['COP']:>8.2f}")
        print(f"Part Load Ratio:      {results['PLR']*100:>8.1f}%")

        print("\n--- WATER CONSUMPTION ---")
        print(f"Evaporation:          {results['m_evap_kg_s']:>8.1f} kg/s  ({results['m_evap_kg_s']*3600:>10,.0f} L/hr)")
        print(f"Blowdown:             {results['m_blowdown_kg_s']:>8.1f} kg/s  ({results['m_blowdown_kg_s']*3600:>10,.0f} L/hr)")
        print(f"Total Makeup:         {results['m_makeup_kg_s']:>8.1f} kg/s  ({results['m_makeup_L_hr']:>10,.0f} L/hr)")
        print(f"WUE:                  {wue:>8.3f} L/kWh")
        print(f"Annual Water:         {results['m_makeup_kg_s']*3600*8760/1e9:>8.1f} million m³/year")
        print(f"COC:                  {results['COC']:>8.1f}")

        print("\n--- TEMPERATURES ---")
        print(f"Ambient Wet Bulb:     {results['T_wb_C']:>8.1f}°C")
        print(f"GPU Coolant Out:      {results['T_gpu_out_C']:>8.1f}°C  (limit: {self.gpu_load.max_temp:.0f}°C) {'✓' if results['gpu_temp_ok'] else '✗'}")
        print(f"Building Air Out:     {results['T_air_out_C']:>8.1f}°C  (limit: {self.building_load.max_temp:.0f}°C) {'✓' if results['building_temp_ok'] else '✗'}")
        print(f"CHW Supply/Return:    {results['state_points']['T1_chw_supply']:>8.1f}°C / {results['state_points']['T4_chw_return']:.1f}°C")
        print(f"CW Range:             {results['state_points']['T9_cw_from_chiller'] - results['state_points']['T8_cw_from_tower']:>8.1f}°C")
        print(f"CT Approach:          {results['state_points']['T8_cw_from_tower'] - results['T_wb_C']:>8.1f}°C")

        print("\n--- VALIDATION ---")
        print(f"Energy Balance Error: {results['energy_balance_error_pct']:>8.4f}%")
        print(f"Convergence:          {'Yes' if results['converged'] else 'No'} ({results['iterations']} iterations)")
        if not results['converged']:
            print(f"Max Temperature Change: {results['max_change_C']:>6.4f}°C (tolerance: {0.01}°C)")

        print("="*70 + "\n")
