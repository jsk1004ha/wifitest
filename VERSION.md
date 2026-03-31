# Version Notes

## 2026-03-30

- Replaced the original `tcp.py` with a structured network diagnostic runner.
- Added explicit probe types for `tcp`, `tls`, `udp_dns`, and `udp_stun`.
- Added a JSON-backed target catalog (`targets.json`) with per-target categories.
- Added optional HTTP URL probes for exact deployed-page checks such as GitHub Pages paths.
- Added CSV export, network labels, probe timestamps, and resolved/probed IP metadata.
- Improved multi-IP handling so TCP/TLS/UDP probes retry each resolved IPv4 address before reporting failure.
- Expanded the default target set with common game and launcher websites including Riot, VALORANT, Steam, Epic, Blizzard, Battle.net, and Nexon properties.
- Removed emoji output so the scripts work in default Windows terminal encodings.
- Fixed UDP hostname resolution and response validation.
- Added CLI flags for timeout control, single-target checks, and JSON export.
- Reworked `UDP.py` into a focused UDP DNS probe with clearer result states.
- Added `README.md` with setup, usage, and interpretation guidance.
- Added `agent.md` with the current program design, scope limits, and implementation phases.
- Improved the WPF controller so engine start failures are surfaced through stderr and exit-code handling instead of appearing as silent launch failures.
- Added clearer UI status transitions for missing engine binaries, startup, running state, and stop/forced-stop paths.

## Scope

- The repository now focuses on measurement and diagnosis only.
- No bypass, spoofing, packet fragmentation, or firewall evasion logic is included.
