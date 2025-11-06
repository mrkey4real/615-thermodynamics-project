#!/usr/bin/env python3
"""
Main Execution Script for 1 GW AI Datacenter Cooling System Model

This script provides multiple operation modes:
1. Single scenario simulation (baseline or optimized)
2. Comparison of baseline vs optimized
3. Time-series simulation with weather data CSV
4. Custom configuration

Usage examples:
    python main.py --scenario baseline
    python main.py --scenario optimized
    python main.py --compare
    python main.py --weather data/weather_example.csv --config config/baseline_config.json
    python main.py --config my_custom_config.json
"""

import argparse
import os
import json
from src.datacenter import DataCenter
from src.utils import (
    WeatherDataLoader,
    load_config,
    save_results,
    validate_energy_balance,
    validate_constraints
)


def run_single_scenario(config_file, output_dir='results', validate=True):
    """
    Run a single datacenter simulation scenario.

    Args:
        config_file: Path to configuration JSON file
        output_dir: Directory for output files
        validate: Whether to run validation checks

    Returns:
        dict: Simulation results
    """
    print(f"\n{'='*70}")
    print(f"Running scenario: {config_file}")
    print(f"{'='*70}")

    # Load configuration
    config = load_config(config_file)

    # Create datacenter
    dc = DataCenter(config)

    # Solve steady state
    results = dc.solve_steady_state(
        utilization=config.get('utilization', 1.0),
        t_wb=config.get('t_wb_ambient')
    )

    # Print summary
    dc.print_summary(results)

    # Validate if requested
    if validate:
        try:
            validate_energy_balance(results, tolerance=1.0)
            validate_constraints(
                results,
                gpu_max_temp=config.get('gpu_max_temp', 40.0),
                building_max_temp=config.get('building_max_temp', 25.0)
            )
            print("\n✓ All validation checks passed!")
        except ValueError as e:
            print(f"\n✗ Validation failed: {e}")

    # Save results
    os.makedirs(output_dir, exist_ok=True)
    scenario_name = config.get('scenario', 'unknown')
    output_file = os.path.join(output_dir, f'{scenario_name}_results.json')
    save_results(results, output_file)
    print(f"\nResults saved to: {output_file}")

    return results


def compare_scenarios(baseline_config, optimized_config, output_dir='results'):
    """
    Compare baseline and optimized scenarios.

    Args:
        baseline_config: Path to baseline configuration
        optimized_config: Path to optimized configuration
        output_dir: Directory for output files
    """
    print(f"\n{'='*70}")
    print("COMPARING BASELINE VS OPTIMIZED SCENARIOS")
    print(f"{'='*70}")

    # Run both scenarios
    baseline_results = run_single_scenario(baseline_config, output_dir, validate=False)
    optimized_results = run_single_scenario(optimized_config, output_dir, validate=False)

    # Calculate metrics
    pue_base = (baseline_results['P_IT_MW'] + baseline_results['W_cooling_total_MW']) / baseline_results['P_IT_MW']
    pue_opt = (optimized_results['P_IT_MW'] + optimized_results['W_cooling_total_MW']) / optimized_results['P_IT_MW']

    wue_base = (baseline_results['m_makeup_kg_s'] * 3600 * 8760) / (baseline_results['P_IT_MW'] * 1000 * 8760)
    wue_opt = (optimized_results['m_makeup_kg_s'] * 3600 * 8760) / (optimized_results['P_IT_MW'] * 1000 * 8760)

    water_savings_pct = (baseline_results['m_makeup_kg_s'] - optimized_results['m_makeup_kg_s']) / baseline_results['m_makeup_kg_s'] * 100
    annual_water_savings_m3 = water_savings_pct / 100 * baseline_results['m_makeup_kg_s'] * 3600 * 8760 / 1000

    # Print comparison
    print(f"\n{'='*70}")
    print("SCENARIO COMPARISON")
    print(f"{'='*70}\n")

    print(f"{'Metric':<30} {'Baseline':>15} {'Optimized':>15} {'Change':>15}")
    print("-" * 77)
    print(f"{'COC':<30} {baseline_results['COC']:>15.1f} {optimized_results['COC']:>15.1f} {'+' + str(int((optimized_results['COC'] - baseline_results['COC']) / baseline_results['COC'] * 100)) + '%':>15}")
    print(f"{'PUE':<30} {pue_base:>15.3f} {pue_opt:>15.3f} {(pue_opt-pue_base):>+15.4f}")
    print(f"{'WUE (L/kWh)':<30} {wue_base:>15.3f} {wue_opt:>15.3f} {(wue_opt-wue_base):>+15.4f}")
    print(f"{'Makeup Water (kg/s)':<30} {baseline_results['m_makeup_kg_s']:>15.1f} {optimized_results['m_makeup_kg_s']:>15.1f} {-water_savings_pct:>+14.1f}%")
    print(f"{'Evaporation (kg/s)':<30} {baseline_results['m_evap_kg_s']:>15.1f} {optimized_results['m_evap_kg_s']:>15.1f} {'~0%':>15}")
    print(f"{'Blowdown (kg/s)':<30} {baseline_results['m_blowdown_kg_s']:>15.1f} {optimized_results['m_blowdown_kg_s']:>15.1f} {-((baseline_results['m_blowdown_kg_s']-optimized_results['m_blowdown_kg_s'])/baseline_results['m_blowdown_kg_s']*100):>+14.1f}%")

    print(f"\n{'Annual Water Savings:':<30} {annual_water_savings_m3:>15,.0f} m³/year")
    print(f"{'Equivalent to city of:':<30} {int(annual_water_savings_m3 / 150):>15,} people")
    print("="*70 + "\n")

    # Save comparison results
    comparison = {
        'baseline': baseline_results,
        'optimized': optimized_results,
        'comparison': {
            'pue_baseline': pue_base,
            'pue_optimized': pue_opt,
            'wue_baseline': wue_base,
            'wue_optimized': wue_opt,
            'water_savings_pct': water_savings_pct,
            'annual_water_savings_m3': annual_water_savings_m3
        }
    }

    output_file = os.path.join(output_dir, 'comparison_results.json')
    save_results(comparison, output_file)
    print(f"Comparison results saved to: {output_file}\n")


def run_weather_series(config_file, weather_csv, output_dir='results'):
    """
    Run time-series simulation with external weather data.

    Args:
        config_file: Path to configuration JSON file
        weather_csv: Path to weather data CSV file
        output_dir: Directory for output files
    """
    print(f"\n{'='*70}")
    print(f"Running time-series simulation with weather data")
    print(f"{'='*70}")

    # Load configuration and weather data
    config = load_config(config_file)
    weather_loader = WeatherDataLoader(weather_csv)

    print(f"\nWeather data loaded: {len(weather_loader.data)} data points")
    min_temp, max_temp = weather_loader.get_temperature_range()
    avg_temp = weather_loader.get_average_temperature()
    print(f"Temperature range: {min_temp:.1f}°C - {max_temp:.1f}°C (avg: {avg_temp:.1f}°C)")

    # Create datacenter
    dc = DataCenter(config)

    # Run simulation for each weather point
    all_results = []
    print("\nRunning simulations...")

    for i, weather_point in enumerate(weather_loader.data):
        t_wb = weather_point['wet_bulb_temp_C']

        # Solve for this weather condition
        results = dc.solve_steady_state(
            utilization=config.get('utilization', 1.0),
            t_wb=t_wb
        )

        results['timestamp'] = weather_point['timestamp']
        results['index'] = i
        all_results.append(results)

        if (i + 1) % 6 == 0 or i == len(weather_loader.data) - 1:
            print(f"  Progress: {i+1}/{len(weather_loader.data)} points completed")

    # Calculate summary statistics
    print(f"\n{'='*70}")
    print("TIME-SERIES SUMMARY STATISTICS")
    print(f"{'='*70}\n")

    avg_pue = sum((r['P_IT_MW'] + r['W_cooling_total_MW']) / r['P_IT_MW'] for r in all_results) / len(all_results)
    avg_cop = sum(r['COP'] for r in all_results) / len(all_results)
    avg_makeup = sum(r['m_makeup_kg_s'] for r in all_results) / len(all_results)

    print(f"Average PUE:                    {avg_pue:.3f}")
    print(f"Average Chiller COP:            {avg_cop:.2f}")
    print(f"Average Makeup Water:           {avg_makeup:.1f} kg/s ({avg_makeup*3600:.0f} L/hr)")
    print(f"Total Simulation Period Water:  {avg_makeup * len(all_results):,.0f} kg")

    # Save results
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, 'weather_series_results.json')
    save_results({'data': all_results, 'summary': {
        'avg_pue': avg_pue,
        'avg_cop': avg_cop,
        'avg_makeup_kg_s': avg_makeup,
        'num_points': len(all_results)
    }}, output_file)
    print(f"\nTime-series results saved to: {output_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='1 GW AI Datacenter Cooling System Model',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Run baseline scenario:
    python main.py --scenario baseline

  Run optimized scenario:
    python main.py --scenario optimized

  Compare baseline vs optimized:
    python main.py --compare

  Run with custom weather data:
    python main.py --weather data/my_weather.csv --config config/baseline_config.json

  Run with custom configuration:
    python main.py --config my_custom_config.json
        """
    )

    parser.add_argument(
        '--scenario',
        choices=['baseline', 'optimized'],
        help='Run predefined scenario (baseline or optimized)'
    )

    parser.add_argument(
        '--compare',
        action='store_true',
        help='Compare baseline vs optimized scenarios'
    )

    parser.add_argument(
        '--config',
        help='Path to custom configuration JSON file'
    )

    parser.add_argument(
        '--weather',
        help='Path to weather data CSV file for time-series simulation'
    )

    parser.add_argument(
        '--output',
        default='results',
        help='Output directory for results (default: results)'
    )

    parser.add_argument(
        '--no-validate',
        action='store_true',
        help='Skip validation checks'
    )

    args = parser.parse_args()

    # Determine operation mode
    if args.compare:
        # Compare mode
        baseline_config = 'config/baseline_config.json'
        optimized_config = 'config/optimized_config.json'
        compare_scenarios(baseline_config, optimized_config, args.output)

    elif args.weather:
        # Weather series mode
        if not args.config:
            print("Error: --weather requires --config to be specified")
            return 1

        if not os.path.exists(args.weather):
            print(f"Error: Weather file not found: {args.weather}")
            return 1

        run_weather_series(args.config, args.weather, args.output)

    elif args.scenario:
        # Single scenario mode (predefined)
        config_file = f'config/{args.scenario}_config.json'
        if not os.path.exists(config_file):
            print(f"Error: Configuration file not found: {config_file}")
            return 1

        run_single_scenario(config_file, args.output, validate=not args.no_validate)

    elif args.config:
        # Single scenario mode (custom config)
        if not os.path.exists(args.config):
            print(f"Error: Configuration file not found: {args.config}")
            return 1

        run_single_scenario(args.config, args.output, validate=not args.no_validate)

    else:
        # Default: run baseline
        print("No operation mode specified. Running baseline scenario...")
        print("(Use --help to see all options)\n")
        config_file = 'config/baseline_config.json'
        run_single_scenario(config_file, args.output, validate=not args.no_validate)

    return 0


if __name__ == '__main__':
    exit(main())
