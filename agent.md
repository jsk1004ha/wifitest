# Agent Design Notes

## Purpose

This repository should build a Windows-friendly network diagnostics tool that helps identify how a local Wi-Fi or managed network is filtering traffic.

The program scope is diagnosis only:
- detect DNS failures
- detect TCP reachability
- detect TLS reachability
- detect UDP responder reachability for known responder protocols such as DNS and STUN
- export repeatable reports for comparison across networks and times

Non-goals:
- firewall evasion
- packet spoofing
- SNI fragmentation
- DNS cloaking
- traffic tunneling
- driver-level interception

## Current Findings

Observed on 2026-03-30 in the current environment:
- most TLS 443 targets in the default set returned `OPEN`, including GitHub, Discord, Riot, Steam, Epic, Blizzard, and Battle.net properties
- `maplestory.nexon.com:443` returned `TIMEOUT` in the latest validation run
- `8.8.8.8:53` returned `OPEN` for UDP DNS in the latest validation run
- `1.1.1.1:53` returned `TIMEOUT` for UDP DNS in the latest validation run
- `stun.l.google.com:3478` returned `OPEN`
- earlier runs on the same date produced different outcomes for some targets, so repeated measurement matters

Interpretation:
- UDP is not universally blocked because STUN responded
- DNS behavior can differ by resolver, so test more than one public DNS endpoint
- HTTPS outcomes may differ by hostname or by momentary network conditions
- timeout alone is not proof of policy blocking; compare across multiple runs and networks when possible

## Product Direction

Build a lightweight desktop diagnostics application with these layers:

1. Probe engine
   - language: Python for current prototype
   - responsibility: run probes concurrently and normalize result states
   - current file: `tcp.py`

2. Target catalog
   - keep a maintained list of common targets by category
   - categories: developer tools, chat, game publishers, storefronts, DNS, realtime UDP services
   - allow custom per-user targets without editing source code

3. Report generator
   - output table to console
   - export JSON for machine-readable history
   - later add CSV export for spreadsheet review

4. UI layer
   - recommended next step: a small desktop UI that can trigger the probe engine and display grouped results
   - if staying in Python, use `tkinter` before considering heavier options
   - if moving to native Windows later, keep the probe engine protocol and result schema stable

## Recommended App Flow

1. User opens the app.
2. App loads a default target catalog plus any saved custom targets.
3. User selects categories or runs the full suite.
4. Engine runs probes concurrently with per-target timeout.
5. UI groups results by category and highlights mixed behavior:
   - DNS fail
   - TLS open
   - TLS timeout
   - UDP open
   - UDP timeout
6. User exports a report with timestamp and network label such as `school_wifi` or `home_wifi`.

## Result Schema

Each probe result should contain:
- `name`
- `category`
- `host`
- `port`
- `check`
- `status`
- `detail`
- `latency_ms`
- `resolved_ips`
- `timestamp`
- `network_label`

Recommended status values:
- `OPEN`
- `DNS_FAIL`
- `TIMEOUT`
- `REFUSED`
- `TLS_FAIL`
- `OS_ERROR`
- `ERROR`

## Target Categories

Suggested default categories:
- `developer`: GitHub main, GitHub raw, GitHub Pages
- `chat`: Discord
- `riot`: Riot Games, League of Legends, VALORANT
- `steam`: Steam Store, Steam Community
- `epic`: Epic Games Store
- `blizzard`: Blizzard, Battle.net
- `nexon`: Nexon main, MapleStory
- `udp_infra`: Google DNS, Cloudflare DNS, Google STUN

## Implementation Plan

### Phase 1

Keep the CLI stable and improve the data model:
- move default targets into a JSON file
- add categories to every target
- add CSV export
- add timestamp and optional network label

### Phase 2

Add a local desktop UI:
- category filters
- run button
- live progress
- grouped results table
- export button

### Phase 3

Add comparison support:
- open two saved reports
- diff result status by target
- show what changes between `home` and `school`

## Validation Rules

After each meaningful change:
- run the default probe suite
- run at least one custom-host probe
- confirm README usage examples still match the code
- update `VERSION.md`

## Editing Guidance

When modifying this repository:
- preserve the diagnosis-only scope
- prefer small, testable changes
- document new targets and new probe types
- avoid adding dependencies unless the built-in standard library is insufficient
