import argparse
import os
import socket
import struct
import time


def build_dns_query(name: str) -> tuple[int, bytes]:
    transaction_id = int.from_bytes(os.urandom(2), "big")
    header = struct.pack("!HHHHHH", transaction_id, 0x0100, 1, 0, 0, 0)
    qname = b"".join(len(part).to_bytes(1, "big") + part.encode("ascii") for part in name.split(".")) + b"\x00"
    question = qname + struct.pack("!HH", 1, 1)
    return transaction_id, header + question


def test_udp_dns(server: str, port: int, timeout: float, query_name: str) -> tuple[str, str, float]:
    started = time.perf_counter()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    target_ip = socket.gethostbyname(server)
    transaction_id, payload = build_dns_query(query_name)

    try:
        sock.sendto(payload, (target_ip, port))
        response, _ = sock.recvfrom(2048)
        response_id = struct.unpack("!H", response[:2])[0]
        if response_id != transaction_id:
            return "ERROR", "unexpected DNS response ID", elapsed_ms(started)
        return "OPEN", "DNS response received", elapsed_ms(started)
    except socket.timeout:
        return "TIMEOUT", "no UDP response received", elapsed_ms(started)
    except OSError as exc:
        return "OS_ERROR", exc.strerror or str(exc), elapsed_ms(started)
    finally:
        sock.close()


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a DNS-formatted UDP probe to a target server.")
    parser.add_argument("--server", default="8.8.8.8", help="UDP server IP or hostname.")
    parser.add_argument("--port", type=int, default=53, help="UDP port.")
    parser.add_argument("--timeout", type=float, default=3.0, help="Socket timeout in seconds.")
    parser.add_argument("--query-name", default="github.com", help="DNS name to query in the test packet.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    status, detail, latency_ms = test_udp_dns(args.server, args.port, args.timeout, args.query_name)
    print(f"server={args.server}:{args.port} status={status} latency_ms={latency_ms:.1f} detail={detail}")


if __name__ == "__main__":
    main()
