# Project Assumptions

This document consolidates the working assumptions embedded in the 1 GW AI datacenter cooling model. Each assumption notes the rationale so future updates can decide whether to keep, relax, or replace it.

## System Scope and Load Breakdown
- **Total IT heat load fixed at 1 GW with a 90/10 GPU to air-cooled split** — Both baseline and optimized configs lock `gpu_load_mw` at 900 and `building_load_mw` at 100 to represent the target 1 GW facility and keep downstream sizing consistent. 【F:config/baseline_config.json†L6-L19】【F:config/optimized_config.json†L6-L19】
- **NVIDIA B200 GPUs at 1.2 kW TDP with 40 °C outlet limit** — The `DataCenter` bootstraps the GPU module with `tdp_per_gpu=1200` and a 40 °C constraint, ensuring the solver matches the intended hardware class and enforces the safe coolant ceiling. 【F:src/datacenter.py†L50-L56】【F:src/gpu_load.py†L24-L108】
- **Air-cooled equipment capped at 25 °C** — Building loads enforce a 25 °C comfort limit so the air loop design remains aligned with typical occupancy requirements. 【F:config/baseline_config.json†L7-L9】【F:src/building_load.py†L24-L102】

## Fluid Properties and Temperature Programs
- **Specific heat of water held at 4,186 J/kg-K for every loop** — GPU, chiller, and cooling tower calculations all reuse this constant, trading some precision for a shared property basis that stabilizes the energy balances. 【F:src/gpu_load.py†L44-L94】【F:src/hvac_system.py†L54-L272】【F:src/datacenter.py†L119-L148】
- **Specific heat of air fixed at 1,005 J/kg-K** — The building loop uses a single cp value at ~20 °C to keep airflow sizing straightforward. 【F:src/building_load.py†L40-L87】
- **Latent heat of vaporization assumed 2,260 kJ/kg** — Cooling tower evaporation uses a constant `h_fg`, simplifying water loss estimates without a psychrometric sub-model. 【F:src/hvac_system.py†L315-L358】
- **Design temperature differences are hard-coded** — GPU loop assumes a 25 °C rise, chilled water loop a 5 °C delta, condenser loop 5.5 °C, and building air loop 5 °C; these deltas set baseline flow rates and avoid iterative sizing. 【F:src/datacenter.py†L119-L143】

## Equipment Performance Models
- **Chiller rated at 1,000 MW with COP 6.1** — The plant is anchored to ASHRAE Path A curves and the rated point embedded in the data file, ensuring compatibility with industry-standard benchmarks. 【F:config/baseline_config.json†L10-L13】【F:data/ashrae_curves.json†L1-L24】【F:src/hvac_system.py†L34-L108】
- **Wet-bulb design point of 25.5 °C with 4 °C approach** — Configuration defaults set the ambient and approach that define condenser water temperatures, grounding tower performance in a warm-humid design day. 【F:config/baseline_config.json†L13-L19】
- **Cycles of concentration preset to 5 (baseline) and 6 (optimized)** — Baseline water management expects COC=5, while the optimized run pushes to 6, framing the comparison studies. 【F:config/baseline_config.json†L13-L21】【F:config/optimized_config.json†L13-L28】
- **Optimized tower COC limited by silica (150 ppm/25 ppm)** — The specialized tower class back-calculates maximum COC from silica chemistry so water savings respect treatment constraints. 【F:config/optimized_config.json†L20-L28】【F:src/hvac_system.py†L512-L565】
- **Cooling tower drift rate fixed at 0.001% of circulation** — `drift_rate=1e-05` is applied for every scenario, aligning with modern induced-draft tower specifications. 【F:config/baseline_config.json†L13-L19】【F:src/hvac_system.py†L315-L338】
- **Fan power pegged at 0.7% of rejected heat** — Tower energy use is proportional to `q_cond`, providing a quick estimate without fan performance curves. 【F:src/hvac_system.py†L426-L477】

## Auxiliary Power and Controls
- **Pump power fractions fixed at 3%, 2%, and 1.5%** — Chilled water, condenser water, and GPU pumps draw fixed fractions of the cooling or GPU loads, supplying parasitic estimates without hydraulic modeling. 【F:src/datacenter.py†L299-L320】
- **Part-load chiller curve cut-off at PLR 0.1** — The ASHRAE `EIRFPLR` input is clipped at 10% load to avoid unrealistic efficiency spikes at very low PLR. 【F:src/hvac_system.py†L154-L170】

## Operational Constraints and Validation
- **GPU coolant and building air limits enforced at 40 °C / 25 °C** — Validation checks reuse the same thresholds, guaranteeing summary reports and guardrails stay in sync. 【F:src/utils.py†L277-L312】
- **Energy balance tolerance set to 1%** — Post-processing treats deviations beyond 1% as model failures, keeping the solver honest about conservation. 【F:src/utils.py†L242-L275】
- **Iteration convergence target of 0.01 °C** — Steady-state solves stop once state-point temperatures change by less than 0.01 °C, giving a practical convergence criterion. 【F:src/datacenter.py†L151-L248】

## Weather and Data Handling
- **Weather driver expects wet-bulb inputs with flexible column names** — The loader auto-detects from a predefined alias list, so external data prep must supply at least one recognized wet-bulb heading. 【F:src/utils.py†L12-L134】
- **Default simulations reuse the ambient wet-bulb from config** — Unless overridden, steady-state runs pick up `t_wb_ambient`, ensuring deterministic baselines. 【F:src/datacenter.py†L174-L224】

Maintaining this list helps distinguish deliberate design targets from placeholders; update the associated code and documentation whenever an assumption changes.
