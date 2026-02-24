\# Power-Agent



Windows system monitoring agent that analyzes battery, CPU, and RAM usage with automated risk assessment and n8n workflow integration.



\## Features



\- Battery monitoring (charge level, power status)

\- Top 5 CPU-intensive processes

\- Top 5 RAM-consuming processes

\- Automated risk assessment (OK / WARN / CRITICAL)

\- Machine-readable METRICS line for n8n parsing

\- Actionable recommendations in German



\## Architecture

Python Script (v12) → Runner (HTTP Server :8787) → n8n Workflow

├── Check CRITICAL (exit\_code 2)

├── Check WARN (exit\_code 1)

└── Status OK (exit\_code 0)



\## Tech Stack



\- Python 3 (psutil, subprocess)

\- n8n workflow automation

\- HTTP Runner on port 8787



\## Exit Codes



| Code | Status | Severity | Trigger |

|------|--------|----------|---------|

| 0 | OK | LOW | All systems normal |

| 1 | WARN | MEDIUM | Battery < 30% or high resource usage |

| 2 | CRITICAL | HIGH | Battery < 10% or system overload |



\## Setup



1\. Install Python dependencies: `pip install psutil`

2\. Start the runner: `python runner.py` (Port 8787)

3\. Import the n8n workflow

4\. Configure Schedule Trigger interval



\## License



GPL-3.0 - see \[LICENSE](LICENSE)

