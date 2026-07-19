# Power-Agent

A small Windows system monitor. It reads the active power plan, the top
processes by CPU time and RAM, and the battery state, then writes a report,
prints a machine-readable summary line, and signals a severity through its
exit code.

The report text is in German — the output is written for its user, not for
publication. The code, on the other hand, uses only the Python standard
library and PowerShell; there are no external dependencies.

## What it does

On each run the script:

- reads the active Windows power plan (`powercfg /getactivescheme`),
- lists the top 5 processes by cumulative CPU time and by RAM working set
  (`Get-Process`, grouped by process name),
- reads the battery charge and status (`Win32_Battery` via CIM),
- derives a risk level of `LOW`, `MEDIUM`, or `HIGH`,
- writes `power_agent_report.txt` next to the script,
- prints a `METRICS:` line and an `ACTION_HINT:` line for machine parsing,
- exits with a code that mirrors the risk level.

## Risk level

The risk level is driven by the battery alone, and only while the battery is
discharging. On AC power it stays `LOW`.

| Risk   | Condition                              | Exit code |
|--------|----------------------------------------|-----------|
| LOW    | on AC power, or charge above 50%       | 0         |
| MEDIUM | discharging and charge at or below 50% | 1         |
| HIGH   | discharging and charge at or below 35% | 2         |

CPU and RAM usage do not change the risk level — they only feed the process
lists and the recommendations. A failure while writing the report also exits
with code 2.

## CPU column

The CPU figure is the **cumulative CPU time in seconds** since each process
started (`Get-Process`'s `CPU` property), not current utilization. Because it
accumulates, long-running processes (for example a local model server) tend to
sit at the top of the list regardless of what they are doing right now. The
report labels this column `CPU-Zeit ges.` to keep that honest.

## Output

`power_agent_report.txt` holds the human-readable report. Two lines in it are
meant for machine parsing:

```
METRICS: battery=33 status=Entlädt risk=HIGH edge_count=9 edge_ram=253 MB ...
ACTION_HINT: close=msedge,claude,code
```

The exit code (0 / 1 / 2) carries the same severity, so a caller can react
without parsing the file.

## Requirements

- Windows
- Python 3 (standard library only — no `pip install` needed)
- PowerShell (ships with Windows)

## Usage

```
py power_agent_report_v12.py
```

The report is written to `power_agent_report.txt` in the same folder, and the
process exits with the risk code above.

## Beyond this repo

The exit code and the `METRICS:` line make the script easy to drive from
something else. In the author's setup a small HTTP runner (port 8787) and an
n8n workflow sit on top and react to the severity on a schedule. Those pieces
are an external layer, not part of this repository.

## License

MIT — see [LICENSE](LICENSE).
