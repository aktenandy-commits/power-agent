from __future__ import annotations
import sys
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REPORT_NAME = "power_agent_report.txt"
TITLE = "POWER-AGENT REPORT"
VERSION = "v12 Exit Codes"
ENCODING = "utf-8"
TOP_PROCESS_COUNT = 5

BATTERY_STATUS = {
    1: "Entlädt",
    2: "Netzbetrieb",
    3: "Voll",
    4: "Schwach",
    5: "Kritisch",
    6: "Lädt",
    7: "Lädt (hoch)",
    8: "Lädt (niedrig)",
    9: "Lädt (kritisch)",
    10: "Unbekannt",
    11: "Teilweise geladen",
}


@dataclass
class ProcessInfo:
    name: str
    pid: int
    cpu: float | None
    ram_bytes: int | None


@dataclass
class ProcessGroup:
    name: str
    count: int
    cpu_total: float | None
    ram_total: int | None
    pid_single: int | None

    @property
    def ram_mb(self) -> str:
        if self.ram_total is None:
            return "-"
        return f"{self.ram_total / (1024 * 1024):.0f} MB"

    @property
    def cpu_formatted(self) -> str:
        if self.cpu_total is None:
            return "-"
        return f"{self.cpu_total:.1f}"

    def __str__(self) -> str:
        if self.count == 1 and self.pid_single is not None:
            return f"{self.name} (PID {self.pid_single}) CPU={self.cpu_formatted} RAM={self.ram_mb}"
        return f"{self.name} ({self.count} Prozesse) CPU={self.cpu_formatted} RAM={self.ram_mb}"


def run_powershell(command: str) -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding=ENCODING,
        errors="replace",
    )
    if result.returncode != 0 and result.stderr:
        print(f"PowerShell-Fehler: {result.stderr.strip()}")
    return (result.stdout or "").strip()


def get_energy_plan() -> str:
    result = subprocess.run(
        ["powercfg", "/getactivescheme"],
        capture_output=True,
        text=True,
        encoding=ENCODING,
        errors="replace",
    )
    text = (result.stdout or "").strip()
    if "(" in text and ")" in text:
        return text.split("(", 1)[1].split(")", 1)[0].strip()
    return text or "Nicht verfügbar"


def get_processes() -> list[ProcessInfo]:
    output = run_powershell(
        "Get-Process | Select-Object Name,Id,CPU,WorkingSet | ConvertTo-Json -Compress"
    )
    if not output:
        return []

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return []

    if isinstance(data, dict):
        data = [data]

    out: list[ProcessInfo] = []
    for p in data:
        out.append(
            ProcessInfo(
                name=p.get("Name", "?"),
                pid=p.get("Id", 0),
                cpu=p.get("CPU"),
                ram_bytes=p.get("WorkingSet"),
            )
        )
    return out


def group_processes(processes: list[ProcessInfo]) -> list[ProcessGroup]:
    buckets: dict[str, list[ProcessInfo]] = {}
    for p in processes:
        buckets.setdefault(p.name, []).append(p)

    groups: list[ProcessGroup] = []
    for name, items in buckets.items():
        cpu_values = [x.cpu for x in items if x.cpu is not None]
        ram_values = [x.ram_bytes for x in items if x.ram_bytes is not None]

        cpu_total = sum(cpu_values) if cpu_values else None
        ram_total = sum(ram_values) if ram_values else None

        pid_single = items[0].pid if len(items) == 1 else None

        groups.append(
            ProcessGroup(
                name=name,
                count=len(items),
                cpu_total=cpu_total,
                ram_total=ram_total,
                pid_single=pid_single,
            )
        )

    return groups


def get_top_by_cpu(groups: list[ProcessGroup], count: int) -> list[ProcessGroup]:
    return sorted(groups, key=lambda g: g.cpu_total or 0, reverse=True)[:count]


def get_top_by_ram(groups: list[ProcessGroup], count: int) -> list[ProcessGroup]:
    return sorted(groups, key=lambda g: g.ram_total or 0, reverse=True)[:count]


def get_battery() -> tuple[bool, int | None, str]:
    output = run_powershell(
        "$b = Get-CimInstance -ClassName Win32_Battery -ErrorAction SilentlyContinue; "
        "if ($null -eq $b) { @{present=$false} | ConvertTo-Json -Compress } "
        "else { @{present=$true; charge=$b.EstimatedChargeRemaining; status=$b.BatteryStatus} | ConvertTo-Json -Compress }"
    )

    try:
        data = json.loads(output) if output else {}
    except json.JSONDecodeError:
        data = {}

    if not data.get("present"):
        return False, None, ""

    charge = data.get("charge")
    status_num = data.get("status")
    status_text = BATTERY_STATUS.get(status_num, f"Unbekannt ({status_num})")

    return True, charge, status_text


def find_group(groups: list[ProcessGroup], name: str) -> ProcessGroup | None:
    for g in groups:
        if g.name.lower() == name.lower():
            return g
    return None


def build_recommendations(
    charge: int | None,
    status: str,
    top_cpu_name: str | None,
    groups: list[ProcessGroup],
) -> list[str]:
    rec: list[str] = []

    if charge is not None and charge < 50 and status == "Entlädt":
        rec.append("Akku unter 50% und entlädt: Helligkeit senken, unnötige Apps schließen, Browser-Tabs reduzieren.")

    if charge is not None and charge < 35 and status == "Entlädt":
        rec.append("Akku unter 35%: Energiesparmodus aktivieren und schwere Apps vermeiden (Video/Browser/AI-Tools).")

    if top_cpu_name:
        if top_cpu_name.lower() in {"msedge", "chrome", "firefox"}:
            rec.append("Top-CPU ist ein Browser: Tabs schließen, Video/Streams stoppen spart sofort Akku.")
        if top_cpu_name.lower() == "copilot":
            rec.append("Top-CPU ist Copilot: wenn nicht gebraucht, schließen/pausieren spart Akku.")

    edge = find_group(groups, "msedge")
    if edge and edge.count >= 8:
        rec.append(f"Browser läuft {edge.count}x ({edge.ram_mb}). Empfehlung: Tabs reduzieren oder Browser-Fenster schließen.")

    claude = find_group(groups, "claude")
    if claude and claude.count >= 5:
        rec.append(f"Claude läuft {claude.count}x ({claude.ram_mb}). Empfehlung: wenn nicht gebraucht komplett schließen.")

    code = find_group(groups, "Code")
    if code and code.count >= 6:
        rec.append(f"VS Code läuft {code.count}x ({code.ram_mb}). Empfehlung: große Projekte schließen oder VS Code neu starten.")

    return rec


def build_report() -> tuple[list[str], str]:
    lines = [
        TITLE,
        f"Version: {VERSION}",
        f"Zeit: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
    ]

    lines.append("Energieplan:")
    lines.append(f"  {get_energy_plan()}")
    lines.append("")

    processes = get_processes()
    groups = group_processes(processes)

    top_cpu = get_top_by_cpu(groups, TOP_PROCESS_COUNT)
    top_ram = get_top_by_ram(groups, TOP_PROCESS_COUNT)

    lines.append(f"Top {TOP_PROCESS_COUNT} Prozesse (CPU):")
    if top_cpu:
        for g in top_cpu:
            lines.append(f"  - {g}")
    else:
        lines.append("  - Keine Daten")
    lines.append("")

    lines.append(f"Top {TOP_PROCESS_COUNT} Prozesse (RAM):")
    if top_ram:
        for g in top_ram:
            lines.append(f"  - {g}")
    else:
        lines.append("  - Keine Daten")
    lines.append("")

    lines.append("Akku:")
    present, charge, status = get_battery()
    if present:
        lines.append(f"  - Ladestand: {charge}%")
        lines.append(f"  - Status: {status}")
    else:
        lines.append("  - Nicht verfügbar")
    lines.append("")

    risk = "LOW"
    if status == "Entlädt" and charge is not None and charge <= 35:
        risk = "HIGH"
    elif status == "Entlädt" and charge is not None and charge <= 50:
        risk = "MEDIUM"

    lines.append(f"RISK: {risk}")
    lines.append("")

    edge = find_group(groups, "msedge")
    code = find_group(groups, "Code")
    claude = find_group(groups, "claude")

    edge_count = edge.count if edge else 0
    code_count = code.count if code else 0
    claude_count = claude.count if claude else 0

    edge_ram = edge.ram_mb if edge else "-"
    code_ram = code.ram_mb if code else "-"
    claude_ram = claude.ram_mb if claude else "-"

    lines.append(
        f"METRICS: battery={charge} status={status} risk={risk} "
        f"edge_count={edge_count} edge_ram={edge_ram} "
        f"code_count={code_count} code_ram={code_ram} "
        f"claude_count={claude_count} claude_ram={claude_ram}"
    )
    lines.append("")

    action_hint = "none"
    if status == "Entlädt" and risk in {"MEDIUM", "HIGH"}:
        action_hint = "close=msedge,claude,code"

    lines.append(f"ACTION_HINT: {action_hint}")
    lines.append("")


    top_cpu_name = top_cpu[0].name if top_cpu else None
    recs = build_recommendations(charge, status, top_cpu_name, groups)

    lines.append("Empfehlungen:")
    if recs and risk in {"MEDIUM", "HIGH"}:

        lines.append("  TOP-EMPFEHLUNG:")
        lines.append("    - Schließe zuerst: Browser-Tabs (msedge), dann Claude, dann VS Code.")

    if recs:
        for r in recs:
            lines.append(f"    - {r}")
    else:
        lines.append("  - Keine")

    return lines, risk




def main() -> None:
    report_path = Path(__file__).resolve().parent / REPORT_NAME
    lines, risk = build_report()

    try:
        report_path.write_text("\n".join(lines), encoding=ENCODING)
        print(f"Report erstellt: {report_path}")
    except OSError as e:
        print(f"Fehler beim Schreiben: {e}")
        sys.exit(2)

    exit_code_map = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    key = str(risk).upper().strip()
    sys.exit(exit_code_map.get(key, 2))


if __name__ == "__main__":
    main()