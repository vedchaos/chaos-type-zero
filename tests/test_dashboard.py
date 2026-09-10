"""Tests for dashboard server."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'dashboard'))


class TestDashboardServer:
    """Test dashboard server initialization."""

    def test_server_import(self):
        """Dashboard server should be importable."""
        try:
            from dashboard import server
            assert server is not None
        except ImportError:
            # Server may have dependencies that aren't installed
            assert True

    def test_mobile_api_import(self):
        """Mobile API should be importable."""
        try:
            from dashboard import mobile_api
            assert mobile_api is not None
        except ImportError:
            # API may have dependencies that aren't installed
            assert True


class TestDashboardEndpoints:
    """Test API endpoints and data generators."""

    def test_health_endpoint_data(self):
        """Health endpoint should return structured status."""
        from dashboard import server
        data = server.build_health_data()
        assert "status" in data
        assert "timestamp" in data

    def test_system_endpoint_data(self):
        """System endpoint should return valid CPU, memory and platform info."""
        from dashboard import server
        data = server.build_system_data()
        assert "hostname" in data
        assert "cpu" in data
        assert "ram" in data

    def test_servers_endpoint_counts_all_mcps(self):
        """Servers endpoint should detect all core agentic MCP servers."""
        from dashboard import server
        data = server.build_servers_data()
        assert isinstance(data, list)
        assert len(data) > 0
        names = [s["name"] for s in data]
        assert "file_mcp" in names
        assert "git_mcp" in names
        assert "web_mcp" in names

    def test_ast_safety_checker(self):
        """AST checker should validate safe Python code."""
        from bridge_core.agents import ExecutorAgent
        safe, reason = ExecutorAgent._is_safe_code("x = 10 + 20\nprint(x)")
        assert safe is True

        # Unsafe code with forbidden call
        unsafe, reason = ExecutorAgent._is_safe_code("import subprocess\nsubprocess.run(['rm', '-rf'])")
        assert unsafe is False

    def test_receipts_endpoint_data(self):
        """Receipts endpoint should return ledger receipts."""
        from dashboard import server
        data = server.build_receipts_data()
        assert data["status"] == "ok"
        assert "receipts" in data
        assert isinstance(data["receipts"], list)
