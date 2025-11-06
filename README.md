# 1 GW AI Datacenter Cooling System Model

A comprehensive thermodynamic model for analyzing cooling systems in large-scale AI datacenters with liquid-cooled GPU clusters. This model provides system-level energy balance calculations, PUE/WUE analysis, and optimization strategies for water conservation.

## Project Overview

**Scale**: 1 GW (1,000 MW) total IT load
- Liquid-cooled GPU Load: 900 MW (90%)
- Air-cooled Equipment Load: 100 MW (10%)

**Key Features**:
- Complete thermodynamic system model with energy balances
- ASHRAE-based chiller performance curves
- Cooling tower transpiration cooling model
- PUE (Power Usage Effectiveness) calculation
- WUE (Water Usage Effectiveness) calculation
- Support for external weather data via CSV import
- Baseline vs. optimized configuration comparison
- Time-series simulation capability

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  COOLING SYSTEM LOOP                     │
│                                                          │
│  Environment (T_wb) ──→ Makeup Water                    │
│         ↓                                                │
│  ┌─────────────────┐                                    │
│  │ Cooling Tower   │ ← Evaporative cooling              │
│  │  - Evaporation  │                                    │
│  │  - Blowdown     │                                    │
│  └────────┬────────┘                                    │
│           ↓ (Condenser Water Loop)                      │
│  ┌─────────────────┐                                    │
│  │    Chiller      │ ← Compressor power                 │
│  │  - Evaporator   │                                    │
│  │  - Condenser    │                                    │
│  └────────┬────────┘                                    │
│           ↓ (Chilled Water Loop)                        │
│      ┌───┴────┐                                         │
│      ↓        ↓                                         │
│  ┌────────┐ ┌────────────────┐                         │
│  │Building│ │     Compute     │                         │
│  │  HVAC  │ │  GPU Coolant   │                         │
│  └───┬────┘ └───┬────────────┘                         │
│      ↓          ↓                                       │
│  ┌────────┐ ┌────────────────┐                         │
│  │  Air   │ │ Liquid Cooled  │                         │
│  │ Cooled │ │  GPU Surfaces  │                         │
│  │  100MW │ │     900MW      │                         │
│  └────────┘ └────────────────┘                         │
└─────────────────────────────────────────────────────────┘
```

## Installation

### Requirements

- Python 3.8 or higher
- NumPy

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd 615-thermodynamics-project
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Verify installation:
```bash
python main.py --help
```

## Usage

### Quick Start

Run the baseline scenario:
```bash
python main.py --scenario baseline
```

Run the optimized scenario:
```bash
python main.py --scenario optimized
```

Compare baseline vs. optimized:
```bash
python main.py --compare
```

### Using Custom Weather Data

The model supports importing weather data from CSV files (e.g., from weather stations):

```bash
python main.py --weather data/my_weather.csv --config config/baseline_config.json
```

**Weather CSV Format** (flexible column names):
```csv
timestamp,wet_bulb_temp_C
2024-01-01 00:00,23.5
2024-01-01 01:00,24.1
...
```

Supported column name variations:
- Wet bulb temperature: `wet_bulb_temp_C`, `t_wb`, `wet_bulb`, `wetbulb`, `T_wb`, etc.
- Timestamp: `timestamp`, `datetime`, `time`, `date`, etc.

### Custom Configuration

Create a custom configuration JSON file:

```json
{
  "description": "My custom datacenter configuration",
  "gpu_load_mw": 900,
  "building_load_mw": 100,
  "chiller_rated_cop": 6.1,
  "cooling_tower_approach": 4.0,
  "coc": 5.0,
  "t_chw_supply": 10.0,
  "t_gpu_in": 15.0,
  "t_air_in": 20.0,
  "t_wb_ambient": 25.5
}
```

Run with custom configuration:
```bash
python main.py --config my_config.json
```

## Project Structure

```
615-thermodynamics-project/
├── src/
│   ├── __init__.py              # Package initialization
│   ├── gpu_load.py              # GPU thermal load model
│   ├── building_load.py         # Building air-cooled load model
│   ├── hvac_system.py           # Chiller and cooling tower models
│   ├── datacenter.py            # System integration
│   └── utils.py                 # Utilities and weather data loader
│
├── data/
│   ├── ashrae_curves.json       # Chiller performance curves
│   └── weather_example.csv      # Example weather data
│
├── config/
│   ├── baseline_config.json     # Baseline configuration (COC=5)
│   └── optimized_config.json    # Optimized configuration (COC=6)
│
├── results/                     # Output directory (auto-created)
│
├── doc/
│   └── MEEN 615 project statement.pdf
│
├── main.py                      # Main execution script
├── requirements.txt             # Python dependencies
├── README.md                    # This file
└── claude.md                    # Technical implementation guide
```

## Component Models

### GPU Load Module (`gpu_load.py`)
Models liquid-cooled GPU cluster thermal load with energy balance calculations.

**Energy Balance**: `Q = m_dot × cp × ΔT`

**Key Parameters**:
- Total load: 900 MW
- GPU model: NVIDIA B200 (1200W TDP)
- Number of GPUs: ~750,000
- Temperature constraint: ≤40°C

### Building Load Module (`building_load.py`)
Models air-cooled equipment thermal load.

**Energy Balance**: `Q = m_dot_air × cp_air × ΔT`

**Key Parameters**:
- Total load: 100 MW
- Temperature constraint: ≤25°C (human comfort)

### Chiller Module (`hvac_system.py`)
Centrifugal water-cooled chiller with ASHRAE performance curves.

**Energy Balances**:
- Evaporator: `Q_evap = m_dot_chw × cp × ΔT`
- Compressor: `W_comp = Q_evap / COP`
- Condenser: `Q_cond = Q_evap + W_comp`

**COP Model**: Based on ASHRAE Standard 90.1 performance curves
- CapFT: Capacity modifier vs. temperature
- EIRFT: EIR modifier vs. temperature
- EIRFPLR: EIR modifier vs. part load ratio

### Cooling Tower Module (`hvac_system.py`)
Induced-draft cooling tower with transpiration cooling.

**Energy Balance**: `Q = m_evap × h_fg`

**Water Balance**:
- Evaporation: Energy-based calculation
- Drift: 0.001% of circulating water
- Blowdown: `m_blowdown = m_evap / (COC - 1)`
- Makeup: `m_makeup = m_evap + m_drift + m_blowdown`

## Performance Metrics

### PUE (Power Usage Effectiveness)
```
PUE = Total Facility Power / IT Equipment Power
PUE = (P_IT + P_cooling) / P_IT
```

**Typical Results**: 1.15 - 1.20

### WUE (Water Usage Effectiveness)
```
WUE = Annual Water Consumption (L) / Annual IT Energy (kWh)
```

**Typical Results**: 0.6 - 0.8 L/kWh

## Optimization Strategy

**Baseline Configuration**: COC = 5.0
**Optimized Configuration**: COC = 6.0

**Water Savings**:
- Blowdown reduction: ~20%
- Total makeup water reduction: ~4-5%
- Annual water savings: ~1 million m³/year

**Trade-offs**:
- Benefit: Reduced water consumption
- Cost: Increased water treatment chemicals
- Requirement: Enhanced water treatment system

## Example Results

### Baseline Scenario (COC = 5)
```
--- PERFORMANCE METRICS ---
PUE:                     1.165
Chiller COP:             6.21
Part Load Ratio:       100.0%

--- WATER CONSUMPTION ---
Evaporation:           508.9 kg/s  (  1,832,056 L/hr)
Blowdown:              127.2 kg/s  (    458,014 L/hr)
Total Makeup:          636.2 kg/s  (  2,290,241 L/hr)
WUE:                   0.737 L/kWh
Annual Water:         20.1 million m³/year
```

### Optimized Scenario (COC = 6)
```
--- PERFORMANCE METRICS ---
PUE:                     1.165
Chiller COP:             6.21
Part Load Ratio:       100.0%

--- WATER CONSUMPTION ---
Evaporation:           508.9 kg/s  (  1,832,056 L/hr)
Blowdown:              101.8 kg/s  (    366,411 L/hr)
Total Makeup:          610.7 kg/s  (  2,198,638 L/hr)
WUE:                   0.707 L/kWh
Annual Water:         19.3 million m³/year

WATER SAVINGS: ~800,000 m³/year (4.0% reduction)
```

## Command-Line Options

```
usage: main.py [-h] [--scenario {baseline,optimized}] [--compare]
               [--config CONFIG] [--weather WEATHER] [--output OUTPUT]
               [--no-validate]

options:
  -h, --help            Show this help message and exit
  --scenario {baseline,optimized}
                        Run predefined scenario
  --compare             Compare baseline vs optimized
  --config CONFIG       Path to custom configuration JSON
  --weather WEATHER     Path to weather data CSV for time-series
  --output OUTPUT       Output directory (default: results)
  --no-validate         Skip validation checks
```

## Remote Deployment

This model is designed to run remotely without any simulation tools. To deploy:

1. Upload project to remote server
2. Install dependencies: `pip install -r requirements.txt`
3. Run simulations: `python main.py --scenario baseline`

The model is pure Python with minimal dependencies (only NumPy) for maximum portability.

## Adding Custom Weather Data

To use your own weather station data:

1. Export data to CSV format with wet bulb temperature
2. Ensure column headers include temperature data (flexible naming)
3. Run: `python main.py --weather your_data.csv --config config/baseline_config.json`

The WeatherDataLoader will automatically detect appropriate columns.

## Validation

The model includes built-in validation checks:

1. **Energy Balance**: Verifies `Q_cond ≈ Q_evap + W_comp` (error < 1%)
2. **Temperature Constraints**: GPU ≤40°C, Building ≤25°C
3. **Physical Limits**: COP > 0, PUE > 1.0, temperatures within range
4. **Convergence**: Iterative solver convergence verification

## Development

### Code Structure

- **Modular design**: Separate GPU and building loads for easy updates
- **Clear interfaces**: Each component has well-defined inputs/outputs
- **Explicit error handling**: No silent failures with `.get()` or broad `try/except`
- **English-only code**: All code, comments, and documentation in English
- **Efficient implementation**: Minimal abstractions, focused on clarity

### Adding New Components

To add a new load type:

1. Create new module in `src/` (e.g., `src/storage_load.py`)
2. Implement class with `calculate_heat_load()` method
3. Update `DataCenter` class to integrate new component
4. Update configuration files with new parameters

## References

- ASHRAE Standard 90.1-2019: Energy Standard for Buildings
- ASHRAE Handbook - HVAC Systems and Equipment
- NVIDIA B200 GPU Specifications
- Datacenter cooling industry best practices

## License

Educational project for MEEN 615 - Thermodynamics course.

## Authors

MEEN 615 Project Team

## Support

For issues or questions:
1. Check the technical implementation guide: `claude.md`
2. Review example configurations in `config/`
3. Check example weather data format in `data/weather_example.csv`

---

**Project Status**: Complete and ready for deployment

**Last Updated**: 2025-11-06
