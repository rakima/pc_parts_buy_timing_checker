from __future__ import annotations

import re


def extract_specifications(category: str, name: str, description: str = "") -> tuple[tuple[str, str], ...]:
    text = f"{name} {description}"
    extractors = {
        "GPU": _gpu_specs,
        "CPU": _cpu_specs,
        "SSD": _ssd_specs,
        "メモリ": _memory_specs,
    }
    specs = extractors.get(category, lambda _text: {})(text)
    return tuple(specs.items())


def format_specifications(specifications: tuple[tuple[str, str], ...]) -> str:
    return " / ".join(f"{key}: {value}" for key, value in specifications)


def _gpu_specs(text: str) -> dict[str, str]:
    specs: dict[str, str] = {}
    model = re.search(r"(?:GeForce\s+)?(RTX\s*\d{4}(?:\s*Ti|\s*SUPER)?)|(?:Radeon\s+)?(RX\s*\d{4}(?:\s*XT)?)", text, re.I)
    if model:
        specs["GPU"] = re.sub(r"\s+", " ", next(value for value in model.groups() if value)).upper()
    memory = re.search(r"(?<![A-Za-z0-9])(\d{1,2})\s*G(?:B|(?=\s|[\]/）)]))(?:\s+GDDR\d+)?", text, re.I)
    if memory:
        specs["VRAM"] = f"{memory.group(1)}GB"
    return specs


def _cpu_specs(text: str) -> dict[str, str]:
    specs: dict[str, str] = {}
    model = re.search(r"(Ryzen\s+(?:Threadripper\s+)?\d(?:\s+PRO)?\s+\d{4,5}[A-Z0-9]*)|(Core(?:\s+Ultra)?\s+[3579]\s+\d{3,5}[A-Z]*)", text, re.I)
    if model:
        specs["CPU"] = re.sub(r"\s+", " ", next(value for value in model.groups() if value))
    socket = re.search(r"Socket\s+(AM\d|LGA\d+|sTRX\d+)", text, re.I)
    if socket:
        specs["ソケット"] = socket.group(1).upper()
    if "クーラー別売" in text:
        specs["クーラー"] = "別売"
    elif "クーラー付属" in text:
        specs["クーラー"] = "付属"
    return specs


def _ssd_specs(text: str) -> dict[str, str]:
    specs: dict[str, str] = {}
    capacity = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*(TB|GB)(?![A-Za-z])", text, re.I)
    if capacity:
        specs["容量"] = f"{capacity.group(1)}{capacity.group(2).upper()}"
    if re.search(r"M\.2", text, re.I):
        specs["形状"] = "M.2"
    elif re.search(r"2\.5\s*インチ", text):
        specs["形状"] = "2.5インチ"
    interface = re.search(r"PCIe\s*(?:Gen)?\s*(\d)(?:\.\d)?\s*x(\d)", text, re.I)
    if interface:
        specs["接続"] = f"PCIe Gen{interface.group(1)}x{interface.group(2)}"
    elif re.search(r"SATA", text, re.I):
        specs["接続"] = "SATA"
    return specs


def _memory_specs(text: str) -> dict[str, str]:
    specs: dict[str, str] = {}
    capacity = re.search(r"(?<!\d)(\d+)\s*GB(?:\s*[（(](\d+)GB\s*[×x]\s*(\d+))?", text, re.I)
    if capacity:
        specs["容量"] = f"{capacity.group(1)}GB"
    generation = re.search(r"DDR([345])", text, re.I)
    if generation:
        specs["規格"] = f"DDR{generation.group(1)}"
    speed = re.search(r"DDR[345]-(\d{4,5})", text, re.I)
    if speed:
        specs["速度"] = speed.group(0).upper()
    latency = re.search(r"CL(\d+)", text, re.I)
    if latency:
        specs["CL"] = latency.group(1)
    return specs
