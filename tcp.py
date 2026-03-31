import argparse
import asyncio
import csv
import ipaddress
import json
import os
import socket
import ssl
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_TARGET_FILE = BASE_DIR / "targets.json"


@dataclass(frozen=True)
class Target:
    name: str
    host: str
    port: int
    check: str
    note: str = ""
    category: str = "custom"
    url: str | None = None


class MultiAddressError(Exception):
    def __init__(self, attempts: list[tuple[str, Exception]]):
        self.attempts = attempts
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        rendered = ", ".join(
            f"{ip}:{type(exc).__name__ or 'Error'}" for ip, exc in self.attempts
        )
        return f"all resolved IPs failed ({rendered})"


def is_ip_address(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


async def resolve_host(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    info = await loop.getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_STREAM)
    return sorted({item[4][0] for item in info})


async def resolve_first_ip(host: str) -> str:
    return (await resolve_host(host))[0]


async def first_success(
    candidates: list[str],
    attempt: Callable[[str], Awaitable[Any]],
) -> tuple[str, Any]:
    failures: list[tuple[str, Exception]] = []
    for candidate in candidates:
        try:
            result = await attempt(candidate)
            return candidate, result
        except Exception as exc:  # pragma: no cover - exercised by tests through MultiAddressError
            failures.append((candidate, exc))
    raise MultiAddressError(failures)


async def tcp_connect(host: str, port: int, timeout: float) -> str:
    resolved_ips = [host] if is_ip_address(host) else await resolve_host(host)

    async def attempt(ip: str) -> None:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port, family=socket.AF_INET),
            timeout=timeout,
        )
        writer.close()
        await writer.wait_closed()

    probe_ip, _ = await first_success(resolved_ips, attempt)
    return probe_ip


async def tls_handshake(host: str, port: int, timeout: float) -> str:
    resolved_ips = [host] if is_ip_address(host) else await resolve_host(host)
    context = ssl.create_default_context()
    server_hostname = None if is_ip_address(host) else host

    async def attempt(ip: str) -> None:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port, ssl=context, server_hostname=server_hostname, family=socket.AF_INET),
            timeout=timeout,
        )
        writer.close()
        try:
            await writer.wait_closed()
        except ssl.SSLError as exc:
            if "APPLICATION_DATA_AFTER_CLOSE_NOTIFY" not in str(exc):
                raise

    probe_ip, _ = await first_success(resolved_ips, attempt)
    return probe_ip


def build_dns_query(name: str) -> tuple[int, bytes]:
    transaction_id = int.from_bytes(os.urandom(2), "big")
    header = struct.pack("!HHHHHH", transaction_id, 0x0100, 1, 0, 0, 0)
    qname = b"".join(len(part).to_bytes(1, "big") + part.encode("ascii") for part in name.split(".")) + b"\x00"
    question = qname + struct.pack("!HH", 1, 1)
    return transaction_id, header + question


async def udp_dns_query(host: str, port: int, timeout: float, query_name: str = "github.com") -> str:
    resolved_ips = [host] if is_ip_address(host) else await resolve_host(host)
    transaction_id, payload = build_dns_query(query_name)

    async def attempt(ip: str) -> None:
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        try:
            await loop.sock_sendto(sock, payload, (ip, port))
            response = await asyncio.wait_for(loop.sock_recv(sock, 2048), timeout=timeout)
            response_id = struct.unpack("!H", response[:2])[0]
            if response_id != transaction_id:
                raise RuntimeError("DNS response transaction ID mismatch")
        finally:
            sock.close()

    probe_ip, _ = await first_success(resolved_ips, attempt)
    return probe_ip


def build_stun_binding_request() -> tuple[bytes, bytes]:
    transaction_id = os.urandom(12)
    payload = struct.pack("!HH", 0x0001, 0) + b"\x21\x12\xa4\x42" + transaction_id
    return transaction_id, payload


async def udp_stun_query(host: str, port: int, timeout: float) -> str:
    resolved_ips = [host] if is_ip_address(host) else await resolve_host(host)
    transaction_id, payload = build_stun_binding_request()

    async def attempt(ip: str) -> None:
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        try:
            await loop.sock_sendto(sock, payload, (ip, port))
            response = await asyncio.wait_for(loop.sock_recv(sock, 2048), timeout=timeout)
            if len(response) < 20:
                raise RuntimeError("Short STUN response")
            if response[4:8] != b"\x21\x12\xa4\x42" or response[8:20] != transaction_id:
                raise RuntimeError("Unexpected STUN response")
        finally:
            sock.close()

    probe_ip, _ = await first_success(resolved_ips, attempt)
    return probe_ip


async def http_fetch(url: str, timeout: float) -> dict[str, Any]:
    def do_request() -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"User-Agent": "WiFiDiag/1.0"})
        context = ssl.create_default_context() if urllib.parse.urlsplit(url).scheme == "https" else None
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            response.read(1)
            return {
                "status_code": response.status,
                "final_url": response.geturl(),
            }

    return await asyncio.to_thread(do_request)


def describe_multi_address_error(exc: MultiAddressError) -> tuple[str, str]:
    if not exc.attempts:
        return "ERROR", "no resolved IPs were available"

    statuses = [map_exception(inner_exc)[0] for _, inner_exc in exc.attempts]
    if statuses and all(status == "TIMEOUT" for status in statuses):
        status = "TIMEOUT"
    elif statuses and all(status == statuses[0] for status in statuses):
        status = statuses[0]
    else:
        status = "ERROR"

    samples = ", ".join(
        f"{ip}={map_exception(inner_exc)[0]}" for ip, inner_exc in exc.attempts[:4]
    )
    if len(exc.attempts) > 4:
        samples += ", ..."
    return status, f"all resolved IPs failed ({samples})"


def map_exception(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, MultiAddressError):
        return describe_multi_address_error(exc)
    if isinstance(exc, urllib.error.HTTPError):
        return "HTTP_ERROR", f"HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, socket.gaierror):
            return "DNS_FAIL", "hostname resolution failed"
        if isinstance(reason, TimeoutError):
            return "TIMEOUT", "no response within timeout"
        return "ERROR", str(reason)
    if isinstance(exc, socket.gaierror):
        return "DNS_FAIL", "hostname resolution failed"
    if isinstance(exc, asyncio.TimeoutError):
        return "TIMEOUT", "no response within timeout"
    if isinstance(exc, ConnectionRefusedError):
        return "REFUSED", "remote host actively refused"
    if isinstance(exc, ssl.SSLError):
        return "TLS_FAIL", str(exc)
    if isinstance(exc, OSError):
        detail = exc.strerror or str(exc)
        return "OS_ERROR", detail
    return "ERROR", str(exc)


async def run_target(target: Target, timeout: float, network_label: str = "") -> dict[str, Any]:
    started = time.perf_counter()
    resolved_ips: list[str] = []
    phase = "resolve"
    probe_ip: str | None = None
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        resolved_ips = [target.host] if is_ip_address(target.host) else await resolve_host(target.host)
        phase = "probe"
        if target.check == "tcp":
            probe_ip = await tcp_connect(target.host, target.port, timeout)
            status = "OPEN"
            detail = f"probe succeeded via {probe_ip}"
        elif target.check == "tls":
            probe_ip = await tls_handshake(target.host, target.port, timeout)
            status = "OPEN"
            detail = f"probe succeeded via {probe_ip}"
        elif target.check == "udp_dns":
            probe_ip = await udp_dns_query(target.host, target.port, timeout)
            status = "OPEN"
            detail = f"probe succeeded via {probe_ip}"
        elif target.check == "udp_stun":
            probe_ip = await udp_stun_query(target.host, target.port, timeout)
            status = "OPEN"
            detail = f"probe succeeded via {probe_ip}"
        elif target.check == "http":
            http_result = await http_fetch(target.url or f"https://{target.host}", timeout)
            status = "OPEN"
            detail = f"HTTP {http_result['status_code']} from {http_result['final_url']}"
        else:
            raise ValueError(f"Unsupported check type: {target.check}")
    except Exception as exc:
        status, detail = map_exception(exc)
        if phase == "probe" and status == "TIMEOUT" and not detail.startswith("all resolved IPs failed"):
            detail = f"{target.check} probe timed out"
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    return {
        "name": target.name,
        "category": target.category,
        "host": target.host,
        "port": target.port,
        "url": target.url,
        "check": target.check,
        "note": target.note,
        "resolved_ips": resolved_ips,
        "ips": resolved_ips,
        "probe_ip": probe_ip,
        "status": status,
        "detail": detail,
        "latency_ms": latency_ms,
        "timestamp": timestamp,
        "network_label": network_label,
    }


def print_report(results: list[dict[str, Any]]) -> None:
    headers = ("category", "check", "name", "target", "status", "latency_ms", "detail")
    rows = [
        (
            item["category"],
            item["check"],
            item["name"],
            item.get("url") or f'{item["host"]}:{item["port"]}',
            item["status"],
            f'{item["latency_ms"]:.1f}',
            item["detail"],
        )
        for item in results
    ]
    widths = [len(column) for column in headers]
    for row in rows:
        widths = [max(current, len(value)) for current, value in zip(widths, row)]

    header_line = " | ".join(title.ljust(width) for title, width in zip(headers, widths))
    divider = "-+-".join("-" * width for width in widths)
    print(header_line)
    print(divider)
    for row in rows:
        print(" | ".join(value.ljust(width) for value, width in zip(row, widths)))


def write_csv(results: list[dict[str, Any]], path: str) -> None:
    fieldnames = [
        "timestamp",
        "network_label",
        "category",
        "name",
        "host",
        "port",
        "url",
        "check",
        "status",
        "detail",
        "latency_ms",
        "probe_ip",
        "resolved_ips",
        "note",
    ]
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in results:
            row = dict(item)
            row["resolved_ips"] = ";".join(item.get("resolved_ips", []))
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def load_default_targets(target_file: Path = DEFAULT_TARGET_FILE) -> list[Target]:
    with open(target_file, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return [Target(**item) for item in payload]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose whether blocks happen at DNS, TCP/TLS, UDP responder, or HTTP page level."
    )
    parser.add_argument("--timeout", type=float, default=3.0, help="Timeout in seconds for each probe.")
    parser.add_argument(
        "--json",
        dest="json_path",
        help="Optional path to write the raw result list as JSON.",
    )
    parser.add_argument(
        "--csv",
        dest="csv_path",
        help="Optional path to write the result list as CSV.",
    )
    parser.add_argument(
        "--network-label",
        default="",
        help="Optional label such as home_wifi or school_wifi to include in exports.",
    )
    parser.add_argument(
        "--host",
        help="Optional single host override. Requires --port and --check.",
    )
    parser.add_argument(
        "--url",
        help="Optional full URL override for exact deployed-page checks. Implies an HTTP probe.",
    )
    parser.add_argument("--port", type=int, help="Port for --host.")
    parser.add_argument(
        "--check",
        choices=["tcp", "tls", "udp_dns", "udp_stun", "http"],
        help="Probe type for --host.",
    )
    parser.add_argument("--name", default="Custom Target", help="Display name for a custom target.")
    parser.add_argument(
        "--target-file",
        default=str(DEFAULT_TARGET_FILE),
        help="JSON file that defines the default target catalog.",
    )
    return parser.parse_args()


def build_targets_from_args(args: argparse.Namespace) -> list[Target]:
    if args.url:
        if args.host:
            raise SystemExit("--url cannot be combined with --host")
        parsed = urllib.parse.urlsplit(args.url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise SystemExit("--url must include http:// or https:// and a hostname")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return [
            Target(
                name=args.name,
                host=parsed.hostname,
                port=port,
                check="http",
                note="CLI URL override",
                category="custom",
                url=args.url,
            )
        ]
    if args.host:
        if args.port is None or args.check is None:
            raise SystemExit("--host requires both --port and --check")
        return [Target(args.name, args.host, args.port, args.check, "CLI override")]
    return load_default_targets(Path(args.target_file))


async def main() -> None:
    args = parse_args()
    targets = build_targets_from_args(args)
    results = await asyncio.gather(
        *(run_target(target, args.timeout, network_label=args.network_label) for target in targets)
    )
    print_report(results)
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=2, ensure_ascii=False)
    if args.csv_path:
        write_csv(results, args.csv_path)


if __name__ == "__main__":
    asyncio.run(main())
