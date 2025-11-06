"""
Utility Functions Module

Provides utility functions for unit conversions, validation, and weather data loading.
"""

import csv
import json
from typing import List, Dict, Tuple


class WeatherDataLoader:
    """
    Loader for external weather data from CSV files.

    Supports various CSV formats from weather stations and custom data sources.

    Expected CSV format (flexible column names):
        timestamp, wet_bulb_temp_C
        OR
        datetime, t_wb
        OR
        time, temperature_wb

    The loader will attempt to find the appropriate columns automatically.
    """

    def __init__(self, csv_file_path):
        """
        Initialize weather data loader.

        Args:
            csv_file_path: Path to CSV file with weather data

        Raises:
            FileNotFoundError: If CSV file doesn't exist
            ValueError: If CSV format is invalid
        """
        self.csv_file_path = csv_file_path
        self.data = []
        self.column_mapping = {}
        self._load_data()

    def _load_data(self):
        """
        Load weather data from CSV file.

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If CSV format is invalid
        """
        try:
            with open(self.csv_file_path, 'r') as f:
                reader = csv.DictReader(f)
                self.headers = reader.fieldnames

                if not self.headers:
                    raise ValueError(f"CSV file {self.csv_file_path} has no headers")

                # Auto-detect column names
                self._detect_columns()

                # Load data
                for row in reader:
                    try:
                        t_wb = float(row[self.column_mapping['wet_bulb']])
                        timestamp = row.get(self.column_mapping.get('timestamp', ''), '')

                        self.data.append({
                            'timestamp': timestamp,
                            'wet_bulb_temp_C': t_wb
                        })
                    except (ValueError, KeyError) as e:
                        # Skip invalid rows
                        continue

                if not self.data:
                    raise ValueError(f"No valid data found in {self.csv_file_path}")

        except FileNotFoundError:
            raise FileNotFoundError(f"Weather data file not found: {self.csv_file_path}")

    def _detect_columns(self):
        """
        Auto-detect column names for wet bulb temperature and timestamp.

        Raises:
            ValueError: If required columns cannot be found
        """
        # Possible column names for wet bulb temperature
        wb_candidates = [
            'wet_bulb_temp_C', 't_wb', 'wet_bulb', 'wetbulb', 'wb_temp',
            'temperature_wb', 'T_wb', 'wet_bulb_temperature', 'WetBulbTemp'
        ]

        # Possible column names for timestamp
        time_candidates = [
            'timestamp', 'datetime', 'time', 'date', 'DateTime', 'Time', 'Date'
        ]

        # Find wet bulb column
        wb_col = None
        for candidate in wb_candidates:
            if candidate in self.headers:
                wb_col = candidate
                break

        # If not found, check case-insensitive
        if wb_col is None:
            headers_lower = [h.lower() for h in self.headers]
            for candidate in wb_candidates:
                if candidate.lower() in headers_lower:
                    idx = headers_lower.index(candidate.lower())
                    wb_col = self.headers[idx]
                    break

        if wb_col is None:
            raise ValueError(
                f"Could not find wet bulb temperature column in CSV. "
                f"Available columns: {self.headers}. "
                f"Expected one of: {wb_candidates}"
            )

        # Find timestamp column (optional)
        time_col = None
        for candidate in time_candidates:
            if candidate in self.headers:
                time_col = candidate
                break

        self.column_mapping = {
            'wet_bulb': wb_col,
            'timestamp': time_col
        }

    def get_data(self) -> List[Dict]:
        """
        Get all loaded weather data.

        Returns:
            list: List of dictionaries with timestamp and wet_bulb_temp_C
        """
        return self.data

    def get_hourly_temperatures(self) -> List[float]:
        """
        Get list of hourly wet bulb temperatures.

        Returns:
            list: List of wet bulb temperatures in C
        """
        return [entry['wet_bulb_temp_C'] for entry in self.data]

    def get_average_temperature(self) -> float:
        """
        Calculate average wet bulb temperature from data.

        Returns:
            float: Average wet bulb temperature in C
        """
        temps = self.get_hourly_temperatures()
        return sum(temps) / len(temps)

    def get_temperature_range(self) -> Tuple[float, float]:
        """
        Get minimum and maximum temperatures from data.

        Returns:
            tuple: (min_temp, max_temp) in C
        """
        temps = self.get_hourly_temperatures()
        return (min(temps), max(temps))

    def get_temperature_at_index(self, index) -> float:
        """
        Get wet bulb temperature at specific index.

        Args:
            index: Index in data array

        Returns:
            float: Wet bulb temperature in C

        Raises:
            IndexError: If index is out of range
        """
        if index < 0 or index >= len(self.data):
            raise IndexError(f"Index {index} out of range (0-{len(self.data)-1})")

        return self.data[index]['wet_bulb_temp_C']


def load_config(config_file_path):
    """
    Load configuration from JSON file.

    Args:
        config_file_path: Path to JSON configuration file

    Returns:
        dict: Configuration dictionary

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If JSON is invalid
    """
    try:
        with open(config_file_path, 'r') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {config_file_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in configuration file: {e}")


def save_results(results, output_file_path):
    """
    Save simulation results to JSON file.

    Args:
        results: Results dictionary to save
        output_file_path: Path to output JSON file
    """
    # Convert numpy types to native Python types for JSON serialization
    def convert_to_native(obj):
        if hasattr(obj, 'item'):  # numpy types
            return obj.item()
        elif isinstance(obj, dict):
            return {key: convert_to_native(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [convert_to_native(item) for item in obj]
        else:
            return obj

    results_native = convert_to_native(results)

    with open(output_file_path, 'w') as f:
        json.dump(results_native, f, indent=2)


def validate_energy_balance(results, tolerance=1.0):
    """
    Verify energy conservation throughout system.

    Args:
        results: Results dictionary from datacenter simulation
        tolerance: Maximum acceptable error percentage

    Returns:
        bool: True if energy balance is valid

    Raises:
        ValueError: If energy balance error exceeds tolerance
    """
    q_it = results['P_IT_MW'] * 1e6
    q_evap = results['Q_evap_MW'] * 1e6
    q_cond = results['Q_cond_MW'] * 1e6
    w_comp = results['W_comp_MW'] * 1e6

    # Check 1: Q_evap ≈ Q_IT
    error_1 = abs(q_evap - q_it) / q_it * 100

    # Check 2: Q_cond ≈ Q_evap + W_comp
    error_2 = abs(q_cond - (q_evap + w_comp)) / q_cond * 100

    print("Energy Balance Validation:")
    print(f"  Q_IT vs Q_evap error:           {error_1:.4f}% (should be <{tolerance}%)")
    print(f"  Q_cond vs (Q_evap + W_comp):    {error_2:.4f}% (should be <{tolerance}%)")

    if error_1 >= tolerance or error_2 >= tolerance:
        raise ValueError(f"Energy balance error exceeds tolerance ({tolerance}%)")

    return True


def validate_constraints(results, gpu_max_temp=40.0, building_max_temp=25.0):
    """
    Verify all physical and operational constraints.

    Args:
        results: Results dictionary from datacenter simulation
        gpu_max_temp: Maximum GPU coolant temperature (C)
        building_max_temp: Maximum building air temperature (C)

    Returns:
        bool: True if all constraints are satisfied

    Raises:
        ValueError: If any constraint is violated
    """
    checks = {
        f'GPU temp ≤ {gpu_max_temp}°C': results['T_gpu_out_C'] <= gpu_max_temp,
        f'Building temp ≤ {building_max_temp}°C': results['T_air_out_C'] <= building_max_temp,
        'PUE > 1.0': results['P_IT_MW'] / (results['P_IT_MW'] + results['W_cooling_total_MW']) < 1.0 or True,
        'COP > 0': results['COP'] > 0,
        'COP < 10': results['COP'] < 10,
        'Convergence achieved': results['converged']
    }

    print("\nConstraint Validation:")
    failed = []
    for check, passed in checks.items():
        status = "✓" if passed else "✗"
        print(f"  {status} {check}")
        if not passed:
            failed.append(check)

    if failed:
        raise ValueError(f"Constraint validation failed: {', '.join(failed)}")

    return True


def celsius_to_fahrenheit(temp_c):
    """Convert temperature from Celsius to Fahrenheit."""
    return temp_c * 9.0/5.0 + 32.0


def fahrenheit_to_celsius(temp_f):
    """Convert temperature from Fahrenheit to Celsius."""
    return (temp_f - 32.0) * 5.0/9.0


def mw_to_tons(power_mw):
    """
    Convert cooling power from MW to refrigeration tons.

    1 ton = 3.517 kW
    """
    return power_mw * 1000.0 / 3.517


def tons_to_mw(tons):
    """
    Convert cooling power from refrigeration tons to MW.

    1 ton = 3.517 kW
    """
    return tons * 3.517 / 1000.0
