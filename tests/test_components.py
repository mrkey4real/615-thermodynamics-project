"""
Test suite for refactored thermodynamic modeling components.

Tests:
- Psychrometric properties
- Refrigeration cycle
- Chiller with vapor compression cycle
- Cooling tower with psychrometric analysis
- Full datacenter system integration
"""

import pytest

from src.datacenter import DataCenter
from src.hvac_system import Chiller, CoolingTower
from src.psychrometrics import PsychrometricState
from src.refrigerant_cycle import COOLPROP_AVAILABLE, VaporCompressionCycle


class TestPsychrometrics:
    """Test psychrometric property calculations."""

    def test_standard_conditions(self):
        """Test air state at 25°C, 50% RH."""
        state = PsychrometricState(T_db_C=25.0, RH=0.5)

        # Check properties are reasonable
        assert 0.009 < state.w < 0.011, f"Humidity ratio {state.w} out of expected range"
        assert 49000 < state.h < 51000, f"Enthalpy {state.h} out of expected range"
        assert 1.1 < state.rho < 1.2, f"Density {state.rho} out of expected range"

    def test_saturated_air(self):
        """Test saturated air at 30°C."""
        state = PsychrometricState(T_db_C=30.0, RH=1.0)

        assert state.RH > 0.99, "Should be saturated"
        assert state.w > 0.025, "Humidity ratio should be high for saturated air"


@pytest.mark.skipif(not COOLPROP_AVAILABLE, reason="CoolProp not available")
class TestRefrigerationCycle:
    """Test vapor compression refrigeration cycle."""

    def test_basic_cycle(self):
        """Test 1 MW cooling capacity cycle."""
        cycle = VaporCompressionCycle(refrigerant="R134a", eta_is_comp=0.80)

        result = cycle.solve(T_evap_C=5.0, T_cond_C=40.0, Q_evap_required=1.0e6)  # 1 MW

        # Check energy balance
        assert result["Q_cond_W"] > result["Q_evap_W"], "Condenser heat > evaporator heat"
        assert result["COP"] > 4.0, f"COP {result['COP']} too low"
        assert result["COP"] < 7.0, f"COP {result['COP']} unrealistically high"

        # Check energy balance error
        Q_balance = result["Q_evap_W"] + result["W_comp_W"]
        error = abs(Q_balance - result["Q_cond_W"]) / result["Q_cond_W"]
        assert error < 0.001, f"Energy balance error {error*100:.4f}% > 0.1%"


@pytest.mark.skipif(not COOLPROP_AVAILABLE, reason="CoolProp not available")
class TestChiller:
    """Test refactored chiller with refrigeration cycle."""

    def test_chiller_convergence(self):
        """Test chiller converges for 1000 MW load."""
        chiller = Chiller(
            rated_capacity_mw=1000, rated_cop=6.1, t_chw_supply=10.0, refrigerant="R134a"
        )

        result = chiller.solve_energy_balance(
            q_evap=1000e6,  # 1000 MW
            m_dot_chw=47800,  # kg/s for 5°C rise
            m_dot_cw=50000,  # kg/s
            t_cw_in=29.5,
        )

        assert result["converged"], "Chiller did not converge"
        assert result["iterations"] < 15, f"Too many iterations: {result['iterations']}"
        assert 5.0 < result["COP"] < 7.0, f"COP {result['COP']} out of range"

        # Check energy balance
        assert (
            result["energy_balance_error_pct"] < 0.01
        ), f"Energy balance error {result['energy_balance_error_pct']:.4f}% too high"


class TestCoolingTower:
    """Test refactored cooling tower with psychrometric analysis."""

    def test_cooling_tower_basic(self):
        """Test cooling tower for 1150 MW heat rejection."""
        tower = CoolingTower(approach_temp=4.0, coc=5.0)

        result = tower.solve(q_cond=1150e6, m_dot_cw=50000, t_in=35.0, t_wb=25.5)  # 1150 MW  # kg/s

        # Check temperatures
        assert result["T_water_out_C"] == pytest.approx(
            29.5, rel=0.01
        ), f"Water outlet temp {result['T_water_out_C']} != 29.5°C"
        assert result["Range_C"] > 5.0, "Range too small"
        assert result["Approach_C"] == 4.0, "Approach should match input"

        # Check psychrometric states
        assert result["RH_out"] > 0.9, "Outlet air should be nearly saturated"
        assert (
            result["w_out_kg_kg"] > result["w_in_kg_kg"]
        ), "Outlet humidity ratio should be > inlet"

        # Energy balance (allow up to 20% error due to psychrometric approximations)
        assert (
            result["energy_balance_error_pct"] < 20.0
        ), f"Energy balance error {result['energy_balance_error_pct']:.2f}% too high"


@pytest.mark.skipif(not COOLPROP_AVAILABLE, reason="CoolProp not available")
class TestDataCenterSystem:
    """Test full datacenter system integration."""

    def test_system_convergence(self):
        """Test 1 GW datacenter system converges."""
        config = {
            "gpu_load_mw": 900,
            "building_load_mw": 100,
            "chiller_rated_cop": 6.1,
            "cooling_tower_approach": 4.0,
            "coc": 5.0,
            "t_chw_supply": 10.0,
            "t_gpu_in": 15.0,
            "t_air_in": 20.0,
            "t_wb_ambient": 25.5,
        }

        dc = DataCenter(config)
        results = dc.solve_steady_state(utilization=1.0)

        assert results["converged"], "System did not converge"
        assert results["iterations"] < 10, f"Too many iterations: {results['iterations']}"

        # Check temperature constraints
        assert results["gpu_temp_ok"], "GPU temperature constraint violated"
        assert results["building_temp_ok"], "Building temperature constraint violated"

        # Check energy balance
        assert (
            results["energy_balance_error_pct"] < 0.1
        ), f"Energy balance error {results['energy_balance_error_pct']:.4f}% too high"

    def test_pue_reasonable(self):
        """Test PUE is in reasonable range."""
        config = {
            "gpu_load_mw": 900,
            "building_load_mw": 100,
            "chiller_rated_cop": 6.1,
            "cooling_tower_approach": 4.0,
            "coc": 5.0,
            "t_chw_supply": 10.0,
            "t_gpu_in": 15.0,
            "t_air_in": 20.0,
            "t_wb_ambient": 25.5,
        }

        dc = DataCenter(config)
        results = dc.solve_steady_state(utilization=1.0)
        pue = dc.calculate_pue(results)

        assert 1.1 < pue < 1.5, f"PUE {pue:.3f} out of reasonable range [1.1, 1.5]"

    def test_wue_reasonable(self):
        """Test WUE is in reasonable range."""
        config = {
            "gpu_load_mw": 900,
            "building_load_mw": 100,
            "chiller_rated_cop": 6.1,
            "cooling_tower_approach": 4.0,
            "coc": 5.0,
            "t_chw_supply": 10.0,
            "t_gpu_in": 15.0,
            "t_air_in": 20.0,
            "t_wb_ambient": 25.5,
        }

        dc = DataCenter(config)
        results = dc.solve_steady_state(utilization=1.0)
        wue = dc.calculate_wue(results)

        assert 0.5 < wue < 5.0, f"WUE {wue:.3f} L/kWh out of reasonable range [0.5, 5.0]"
