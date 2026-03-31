# WiFi Blocking Diagnostics

This repository contains small Python probes that help identify where a network block is happening.

The tools are intentionally limited to diagnostics:
- DNS resolution failures
- TCP or TLS reachability
- UDP responders such as DNS or STUN

They do not implement packet spoofing, fragmentation, or firewall evasion.

## Files

- `tcp.py`: main diagnostic runner for DNS, TCP/TLS, UDP responder, and exact HTTP URL checks
- `UDP.py`: focused UDP DNS probe for quick testing
- `agent.md`: current product direction, architecture notes, and validation rules

## Requirements

- Python 3.11 or newer
- Outbound network access from the machine running the script

## Usage

Run the default test set:

```powershell
python tcp.py
```

The default set is loaded from `targets.json` and includes:
- GitHub and Discord
- Riot Games, League of Legends, VALORANT
- Steam Store and Steam Community
- Epic Games Store
- Blizzard and Battle.net
- Nexon and MapleStory
- UDP DNS and STUN checks

Increase timeout:

```powershell
python tcp.py --timeout 5
```

Test a single host:

```powershell
python tcp.py --host github.com --port 443 --check tls --name "GitHub TLS"
```

Test an exact deployed page URL:

```powershell
python tcp.py --url https://jsk1004ha.github.io/CHRONO-BREAK/ --name "CHRONO-BREAK"
```

Examples for game-related sites:

```powershell
python tcp.py --host www.leagueoflegends.com --port 443 --check tls --name "LoL Site"
python tcp.py --host playvalorant.com --port 443 --check tls --name "VALORANT Site"
python tcp.py --host shop.battle.net --port 443 --check tls --name "Battle.net Shop"
python tcp.py --host maplestory.nexon.com --port 443 --check tls --name "MapleStory"
```

Save raw output:

```powershell
python tcp.py --json report.json
```

Save CSV output with a network label:

```powershell
python tcp.py --network-label school_wifi --csv report.csv
```

Run the UDP DNS probe directly:

```powershell
python UDP.py --server 8.8.8.8 --port 53 --query-name github.com
```

## Status Guide

- `OPEN`: the probe completed successfully
- `DNS_FAIL`: hostname resolution failed before the network probe
- `TIMEOUT`: no response arrived before the timeout
- `REFUSED`: the remote endpoint actively rejected the connection
- `TLS_FAIL`: TCP opened, but TLS negotiation failed
- `OS_ERROR`: the local socket stack returned a system error
- `ERROR`: an unexpected error occurred

## Interpreting Results

- `DNS_FAIL` usually points to local DNS issues, DNS interception, or a bad hostname.
- `TIMEOUT` on `tls` can mean upstream filtering, packet loss, or a slow path. It is not proof by itself. When a host resolves to multiple IPv4 addresses, the tool now reports whether all resolved IPs timed out.
- `TIMEOUT` on UDP only means no response was observed. Many UDP services ignore unknown payloads, so treat it as a clue, not a verdict.
- Comparing `tls` results between `github.com`, `raw.githubusercontent.com`, and a self-hosted site is often more useful than testing a single target.

## Notes

- The default targets are examples and can be changed in `targets.json`.
- For blocked GitHub Pages or deployed static sites, prefer `--url` for an exact page/path check and `--host` for raw TCP/TLS reachability.
- The current design direction for a desktop diagnostics app is documented in `agent.md`.
