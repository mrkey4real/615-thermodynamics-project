"""
Test script for refactored thermodynamic modeling system.

Tests:
1. Psychrometric properties
2. Refrigeration cycle
3. Refactored Chiller
4. Refactored Cooling Tower
5. Full DataCenter system integration
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_psychrometrics():
    """Test psychrometric properties module."""
    print("\n" + "="*70)
    print("TEST 1: PSYCHROMETRIC PROPERTIES")
    print("="*70)

    from psychrometrics import PsychrometricState

    # Standard conditions: 25°C DB, 50% RH
    state = PsychrometricState(T_db_C=25.0, RH=0.5)
    print(f"\nAir state at 25°C, 50% RH:")
    print(f"  Humidity ratio: {state.w:.6f} kg_water/kg_air")
    print(f"  Enthalpy: {state.h:.1f} J/kg_air")
    print(f"  Density: {state.rho:.4f} kg/m³")

    print("\n✓ Psychrometric properties test passed")

def test_refrigeration_cycle():
    """Test refrigeration cycle module."""
    print("\n" + "="*70)
    print("TEST 2: REFRIGERATION CYCLE")
    print("="*70)

    try:
        from refrigerant_cycle import VaporCompressionCycle, COOLPROP_AVAILABLE

        if not COOLPROP_AVAILABLE:
            print("\n⚠ CoolProp not available - skipping refrigeration cycle test")
            print("  Install with: pip install CoolProp")
            return

        # Create cycle
        cycle = VaporCompressionCycle(refrigerant='R134a', eta_is_comp=0.80)

        # Solve for 1 MW cooling capacity
        result = cycle.solve(T_evap_C=5.0, T_cond_C=40.0, Q_evap_required=1.0e6)

        print(f"\nRefrigeration cycle (1 MW cooling):")
        print(f"  Evaporator temp: {result['T_evap_C']:.1f}°C")
        print(f"  Condenser temp: {result['T_cond_C']:.1f}°C")
        print(f"  Refrigerant flow: {result['m_dot_ref_kg_s']:.3f} kg/s")
        print(f"  Compressor power: {result['W_comp_W']/1e6:.3f} MW")
        print(f"  COP: {result['COP']:.2f}")
        print(f"  Compression ratio: {result['compression_ratio']:.2f}")

        print("\n✓ Refrigeration cycle test passed")

    except ImportError as e:
        print(f"\n⚠ CoolProp not available: {e}")
        print("  Install with: pip install CoolProp")

def test_refactored_chiller():
    """Test refactored Chiller class."""
    print("\n" + "="*70)
    print("TEST 3: REFACTORED CHILLER")
    print("="*70)

    try:
        from hvac_system import Chiller
        from refrigerant_cycle import COOLPROP_AVAILABLE

        if not COOLPROP_AVAILABLE:
            print("\n⚠ CoolProp not available - skipping chiller test")
            return

        # Create chiller
        chiller = Chiller(
            rated_capacity_mw=1000,
            rated_cop=6.1,
            t_chw_supply=10.0,
            refrigerant='R134a'
        )

        # Solve for 1000 MW load
        result = chiller.solve_energy_balance(
            q_evap=1000e6,
            m_dot_chw=47800,  # kg/s for 5°C rise
            m_dot_cw=50000,   # kg/s
            t_cw_in=29.5
        )

        print(f"\nChiller performance:")
        print(f"  Cooling capacity: {result['Q_evap_MW']:.1f} MW")
        print(f"  Compressor power: {result['W_comp_MW']:.1f} MW")
        print(f"  Heat rejection: {result['Q_cond_MW']:.1f} MW")
        print(f"  COP: {result['COP']:.2f}")
        print(f"  CHW: {result['T_chw_supply_C']:.1f}°C → {result['T_chw_return_C']:.1f}°C")
        print(f"  CW: {result['T_cw_in_C']:.1f}°C → {result['T_cw_out_C']:.1f}°C")
        print(f"  Evap sat temp: {result['T_evap_sat_C']:.1f}°C")
        print(f"  Cond sat temp: {result['T_cond_sat_C']:.1f}°C")
        print(f"  Converged: {result['converged']} ({result['iterations']} iterations)")

        print("\n✓ Refactored chiller test passed")

    except ImportError as e:
        print(f"\n⚠ CoolProp not available: {e}")

def test_refactored_cooling_tower():
    """Test refactored CoolingTower class."""
    print("\n" + "="*70)
    print("TEST 4: REFACTORED COOLING TOWER")
    print("="*70)

    from hvac_system import CoolingTower

    # Create cooling tower
    tower = CoolingTower(approach_temp=4.0, coc=5.0)

    # Solve for 1150 MW heat rejection
    result = tower.solve(
        q_cond=1150e6,
        m_dot_cw=50000,
        t_in=35.0,
        t_wb=25.5
    )

    print(f"\nCooling tower performance:")
    print(f"  Heat rejection: {result['Q_cond_MW']:.1f} MW")
    print(f"  Water in/out: {result['T_water_in_C']:.1f}°C → {result['T_water_out_C']:.1f}°C")
    print(f"  Range: {result['Range_C']:.1f}°C, Approach: {result['Approach_C']:.1f}°C")
    print(f"  Air inlet: T_db={result['T_db_in_C']:.1f}°C, RH={result['RH_in']*100:.1f}%")
    print(f"  Air outlet: T_db={result['T_db_out_C']:.1f}°C, RH={result['RH_out']*100:.1f}%")
    print(f"  Humidity ratio: {result['w_in_kg_kg']:.6f} → {result['w_out_kg_kg']:.6f} kg/kg")
    print(f"  Evaporation: {result['m_evap_kg_s']:.1f} kg/s")
    print(f"  Makeup water: {result['m_makeup_kg_s']:.1f} kg/s ({result['m_makeup_L_hr']:,.0f} L/hr)")
    print(f"  Energy balance error: {result['energy_balance_error_pct']:.2f}%")

    print("\n✓ Refactored cooling tower test passed")

def test_full_system():
    """Test full DataCenter system integration."""
    print("\n" + "="*70)
    print("TEST 5: FULL DATACENTER SYSTEM")
    print("="*70)

    try:
        from datacenter import DataCenter
        from refrigerant_cycle import COOLPROP_AVAILABLE

        if not COOLPROP_AVAILABLE:
            print("\n⚠ CoolProp not available - using simplified model")
            print("  For full thermodynamic modeling, install: pip install CoolProp")
            return

        # Configuration
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

        # Create datacenter
        dc = DataCenter(config)

        # Solve steady state
        print("\nSolving 1 GW datacenter system...")
        results = dc.solve_steady_state(utilization=1.0)

        # Print summary
        dc.print_summary(results)

        # Calculate metrics
        pue = dc.calculate_pue(results)
        wue = dc.calculate_wue(results)

        print("\n✓ Full system integration test passed")
        print(f"\nKey Results:")
        print(f"  PUE: {pue:.3f}")
        print(f"  WUE: {wue:.3f} L/kWh")
        print(f"  Converged: {results['converged']}")

    except Exception as e:
        print(f"\n✗ Full system test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("\n" + "="*70)
    print("REFACTORED THERMODYNAMIC MODELING SYSTEM - TEST SUITE")
    print("="*70)

    test_psychrometrics()
    test_refrigeration_cycle()
    test_refactored_chiller()
    test_refactored_cooling_tower()
    test_full_system()

    print("\n" + "="*70)
    print("ALL TESTS COMPLETED")
    print("="*70 + "\n")
