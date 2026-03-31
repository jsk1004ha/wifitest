import argparse
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tcp


class TcpTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_success_tries_later_candidate(self):
        attempts = []

        async def attempt(candidate: str) -> str:
            attempts.append(candidate)
            if candidate == "first":
                raise asyncio.TimeoutError()
            return "ok"

        candidate, result = await tcp.first_success(["first", "second"], attempt)
        self.assertEqual(candidate, "second")
        self.assertEqual(result, "ok")
        self.assertEqual(attempts, ["first", "second"])

    async def test_run_target_reports_multi_ip_timeout(self):
        target = tcp.Target("demo", "example.com", 443, "tls")
        with mock.patch("tcp.resolve_host", new=mock.AsyncMock(return_value=["1.1.1.1", "2.2.2.2"])):
            with mock.patch("tcp.tls_handshake", new=mock.AsyncMock(side_effect=tcp.MultiAddressError([
                ("1.1.1.1", asyncio.TimeoutError()),
                ("2.2.2.2", asyncio.TimeoutError()),
            ]))):
                result = await tcp.run_target(target, timeout=0.1)
        self.assertEqual(result["status"], "TIMEOUT")
        self.assertIn("all resolved IPs failed", result["detail"])

    async def test_run_target_http_success(self):
        target = tcp.Target(
            name="demo-url",
            host="example.com",
            port=443,
            check="http",
            url="https://example.com/demo",
        )
        with mock.patch("tcp.resolve_host", new=mock.AsyncMock(return_value=["93.184.216.34"])):
            with mock.patch("tcp.http_fetch", new=mock.AsyncMock(return_value={"status_code": 200, "final_url": target.url})):
                result = await tcp.run_target(target, timeout=0.1, network_label="home")
        self.assertEqual(result["status"], "OPEN")
        self.assertEqual(result["network_label"], "home")
        self.assertIn("HTTP 200", result["detail"])


class TcpArgTests(unittest.TestCase):
    def test_build_targets_from_url(self):
        args = argparse.Namespace(
            host=None,
            port=None,
            check=None,
            url="https://example.com/demo",
            name="Example URL",
            target_file=str(Path("targets.json")),
        )
        targets = tcp.build_targets_from_args(args)
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].check, "http")
        self.assertEqual(targets[0].host, "example.com")
        self.assertEqual(targets[0].url, "https://example.com/demo")

    def test_load_default_targets_from_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "targets.json"
            path.write_text(
                '[{"name":"A","host":"example.com","port":443,"check":"tls","category":"dev","note":"x"}]',
                encoding="utf-8",
            )
            targets = tcp.load_default_targets(path)
        self.assertEqual(targets[0].category, "dev")
        self.assertEqual(targets[0].host, "example.com")


if __name__ == "__main__":
    unittest.main()
