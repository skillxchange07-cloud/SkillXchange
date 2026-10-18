"""
SkillXchange — Production Guard and Configuration Verification Tests
Verifies production mode detection, fail-safe environment variable requirements,
Socket.IO CORS origin parsing, development fallbacks, and database URL normalization.
"""
import os
import sys
import unittest
import importlib
from unittest.mock import patch

# Ensure workspace root is in sys.path
WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

import config
from config import is_production, parse_allowed_origins


class ProductionGuardTestSuite(unittest.TestCase):
    """Test suite for production detection and fail-fast startup guards."""

    def _reset_config_state(self):
        """Restore clean testing environment and reload config to avoid polluting other test suites."""
        clean_env = {
            'FLASK_ENV': 'testing',
            'SECRET_KEY': 'clean-test-key-for-test-runner',
            'DATABASE_URL': '',
            'ALLOWED_ORIGINS': '',
            'RENDER': '',
            'ENV': ''
        }
        with patch.dict(os.environ, clean_env, clear=False):
            if 'RENDER' in os.environ:
                del os.environ['RENDER']
            if 'ENV' in os.environ:
                del os.environ['ENV']
            importlib.reload(config)

    def tearDown(self):
        self._reset_config_state()

    @classmethod
    def tearDownClass(cls):
        clean_env = {
            'FLASK_ENV': 'testing',
            'SECRET_KEY': 'clean-test-key-for-test-runner',
            'DATABASE_URL': '',
            'ALLOWED_ORIGINS': '',
            'RENDER': '',
            'ENV': ''
        }
        with patch.dict(os.environ, clean_env, clear=False):
            if 'RENDER' in os.environ:
                del os.environ['RENDER']
            if 'ENV' in os.environ:
                del os.environ['ENV']
            importlib.reload(config)

    # -------------------------------------------------------------------------
    # 1. Explicit FLASK_ENV=production detection
    # -------------------------------------------------------------------------
    def test_01_flask_env_production_detection(self):
        self.assertTrue(is_production({'FLASK_ENV': 'production'}))
        self.assertFalse(is_production({'FLASK_ENV': 'development'}))
        self.assertFalse(is_production({'FLASK_ENV': 'testing'}))

    # -------------------------------------------------------------------------
    # 2. Explicit ENV=production detection
    # -------------------------------------------------------------------------
    def test_02_env_production_detection(self):
        self.assertTrue(is_production({'ENV': 'production'}))
        self.assertFalse(is_production({'ENV': 'development'}))
        self.assertFalse(is_production({'ENV': 'staging'}))

    # -------------------------------------------------------------------------
    # 3. Render environment detection
    # -------------------------------------------------------------------------
    def test_03_render_environment_detection(self):
        self.assertTrue(is_production({'RENDER': 'true'}))
        self.assertTrue(is_production({'RENDER': '1'}))
        self.assertFalse(is_production({'RENDER': 'false'}))
        self.assertFalse(is_production({'RENDER': '0'}))

    # -------------------------------------------------------------------------
    # 4. Case and whitespace handling
    # -------------------------------------------------------------------------
    def test_04_case_and_whitespace_handling(self):
        # Surrounding whitespace and mixed casing
        self.assertTrue(is_production({'FLASK_ENV': '  Production  '}))
        self.assertTrue(is_production({'FLASK_ENV': 'PRODUCTION'}))
        self.assertTrue(is_production({'ENV': '  pRoDuCtIoN  '}))
        self.assertTrue(is_production({'RENDER': '  True  '}))
        self.assertTrue(is_production({'RENDER': '  1  '}))
        self.assertTrue(is_production({'RENDER': 'TRUE'}))

        # Non-production with whitespace
        self.assertFalse(is_production({'FLASK_ENV': '  development  '}))
        self.assertFalse(is_production({'RENDER': '  false  '}))

    # -------------------------------------------------------------------------
    # 5. Missing production secret causes a clear startup error
    # -------------------------------------------------------------------------
    def test_05_missing_production_secret_raises_clear_error(self):
        # Empty string
        with patch.dict(os.environ, {
            'FLASK_ENV': 'production',
            'SECRET_KEY': '',
            'DATABASE_URL': 'postgresql://localhost/db',
            'ALLOWED_ORIGINS': 'https://app.render.com'
        }, clear=False):
            with self.assertRaises(RuntimeError) as ctx:
                importlib.reload(config)
            self.assertIn("SECRET_KEY environment variable must be set in production", str(ctx.exception))

        # Whitespace-only string
        with patch.dict(os.environ, {
            'FLASK_ENV': 'production',
            'SECRET_KEY': '   ',
            'DATABASE_URL': 'postgresql://localhost/db',
            'ALLOWED_ORIGINS': 'https://app.render.com'
        }, clear=False):
            with self.assertRaises(RuntimeError) as ctx:
                importlib.reload(config)
            self.assertIn("SECRET_KEY environment variable must be set in production", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 6. Missing production database URL causes a clear startup error
    # -------------------------------------------------------------------------
    def test_06_missing_production_database_url_raises_clear_error(self):
        with patch.dict(os.environ, {
            'FLASK_ENV': 'production',
            'SECRET_KEY': 'prod-secret-key-12345',
            'DATABASE_URL': '',
            'ALLOWED_ORIGINS': 'https://app.render.com'
        }, clear=False):
            with self.assertRaises(RuntimeError) as ctx:
                importlib.reload(config)
            self.assertIn("DATABASE_URL environment variable must be set in production", str(ctx.exception))

        # Whitespace-only string under RENDER=true
        with patch.dict(os.environ, {
            'RENDER': 'true',
            'SECRET_KEY': 'prod-secret-key-12345',
            'DATABASE_URL': '   ',
            'ALLOWED_ORIGINS': 'https://app.render.com'
        }, clear=False):
            with self.assertRaises(RuntimeError) as ctx:
                importlib.reload(config)
            self.assertIn("DATABASE_URL environment variable must be set in production", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 7. Missing production allowed origins causes a clear startup error
    # -------------------------------------------------------------------------
    def test_07_missing_production_allowed_origins_raises_clear_error(self):
        # Direct function check
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins(None, is_prod=True)
        self.assertIn("ALLOWED_ORIGINS environment variable must be set in production", str(ctx.exception))

        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("   ", is_prod=True)
        self.assertIn("ALLOWED_ORIGINS environment variable must be set in production", str(ctx.exception))

        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("  , ,  ", is_prod=True)
        self.assertIn("ALLOWED_ORIGINS environment variable must contain at least one valid origin", str(ctx.exception))

        # Config reload check
        with patch.dict(os.environ, {
            'FLASK_ENV': 'production',
            'SECRET_KEY': 'prod-secret-key-12345',
            'DATABASE_URL': 'postgresql://localhost/db',
            'ALLOWED_ORIGINS': ''
        }, clear=False):
            with self.assertRaises(RuntimeError) as ctx:
                importlib.reload(config)
            self.assertIn("ALLOWED_ORIGINS environment variable must be set in production", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 8. Explicit comma-separated origins and strict origin syntax validation
    # -------------------------------------------------------------------------
    def test_08a_explicit_comma_separated_origins_parsed_correctly(self):
        raw = " https://skillxchange.onrender.com ,  https://app.example.com  "
        origins = parse_allowed_origins(raw, is_prod=True)
        self.assertEqual(origins, ["https://skillxchange.onrender.com", "https://app.example.com"])

        # Multiple origins in config reload
        with patch.dict(os.environ, {
            'FLASK_ENV': 'production',
            'SECRET_KEY': 'prod-secret-key-12345',
            'DATABASE_URL': 'postgresql://localhost/db',
            'ALLOWED_ORIGINS': raw
        }, clear=False):
            importlib.reload(config)
            self.assertEqual(config.Config.CORS_ALLOWED_ORIGINS, ["https://skillxchange.onrender.com", "https://app.example.com"])

    def test_08b_valid_https_origins_and_optional_trailing_slash(self):
        # Exact HTTPS origin
        origins1 = parse_allowed_origins("https://skillxchange.onrender.com", is_prod=True)
        self.assertEqual(origins1, ["https://skillxchange.onrender.com"])

        # HTTPS origin with optional trailing slash normalized
        origins2 = parse_allowed_origins("https://skillxchange.onrender.com/", is_prod=True)
        self.assertEqual(origins2, ["https://skillxchange.onrender.com"])

    def test_08c_valid_custom_domains_and_ports(self):
        # Custom domain with non-standard port
        origins = parse_allowed_origins("https://mentor.customdomain.org:8443", is_prod=True)
        self.assertEqual(origins, ["https://mentor.customdomain.org:8443"])

        # Localhost with port (valid for local/testing)
        local_origins = parse_allowed_origins("http://localhost:5000, http://127.0.0.1:5000", is_prod=True)
        self.assertEqual(local_origins, ["http://localhost:5000", "http://127.0.0.1:5000"])

        # IPv6 literal with port
        ipv6_origins = parse_allowed_origins("https://[::1]:8080", is_prod=True)
        self.assertEqual(ipv6_origins, ["https://[::1]:8080"])

    def test_08d_missing_schemes_rejected_in_production(self):
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("skillxchange.onrender.com", is_prod=True)
        self.assertIn("Scheme must be 'http' or 'https'", str(ctx.exception))

        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("://skillxchange.onrender.com", is_prod=True)
        self.assertIn("Scheme must be 'http' or 'https'", str(ctx.exception))

        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("ftp://skillxchange.onrender.com", is_prod=True)
        self.assertIn("Scheme must be 'http' or 'https'", str(ctx.exception))

    def test_08e_missing_hostnames_rejected_in_production(self):
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://", is_prod=True)
        self.assertIn("Missing valid hostname", str(ctx.exception))

        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://:8080", is_prod=True)
        self.assertIn("Missing valid hostname", str(ctx.exception))

    def test_08f_paths_rejected_in_production(self):
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://skillxchange.onrender.com/messages", is_prod=True)
        self.assertIn("Origin must not include a path", str(ctx.exception))

        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://skillxchange.onrender.com/api/v1/", is_prod=True)
        self.assertIn("Origin must not include a path", str(ctx.exception))

    def test_08g_query_strings_rejected_in_production(self):
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://skillxchange.onrender.com?query=param", is_prod=True)
        self.assertIn("Origin must not include query parameters", str(ctx.exception))

    def test_08h_fragments_rejected_in_production(self):
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://skillxchange.onrender.com#section", is_prod=True)
        self.assertIn("Origin must not include a fragment", str(ctx.exception))

    def test_08i_multiple_valid_comma_separated_origins(self):
        raw = " https://skillxchange.onrender.com/ , https://customdomain.com , http://localhost:5000 "
        origins = parse_allowed_origins(raw, is_prod=True)
        self.assertEqual(origins, [
            "https://skillxchange.onrender.com",
            "https://customdomain.com",
            "http://localhost:5000"
        ])

    def test_08j_embedded_credentials_rejected_without_leakage(self):
        secret_user = "sensitive_admin"
        secret_pass = "SuperSecretPassword123!"
        credential_origin = f"https://{secret_user}:{secret_pass}@example.com"

        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins(credential_origin, is_prod=True)
        err_msg = str(ctx.exception)
        self.assertIn("Embedded credentials", err_msg)
        # Ensure credentials are NOT leaked in exception message
        self.assertNotIn(secret_user, err_msg)
        self.assertNotIn(secret_pass, err_msg)

        # User only
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins(f"https://{secret_user}@example.com", is_prod=True)
        self.assertNotIn(secret_user, str(ctx.exception))

        # Password only
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins(f"https://:{secret_pass}@example.com", is_prod=True)
        self.assertNotIn(secret_pass, str(ctx.exception))

    def test_08k_ports_safe_validation(self):
        # Valid boundary ports
        origins_low = parse_allowed_origins("https://example.com:1", is_prod=True)
        self.assertEqual(origins_low, ["https://example.com:1"])

        origins_high = parse_allowed_origins("https://example.com:65535", is_prod=True)
        self.assertEqual(origins_high, ["https://example.com:65535"])

        # Non-numeric port
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://example.com:abc", is_prod=True)
        self.assertIn("Port must be a valid integer between 1 and 65535", str(ctx.exception))

        # Empty port string (trailing colon)
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://example.com:", is_prod=True)
        self.assertIn("Port must be a valid integer between 1 and 65535", str(ctx.exception))

        # Port out of range (> 65535)
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://example.com:70000", is_prod=True)
        self.assertTrue(
            "Port must be a valid integer" in str(ctx.exception) or
            "out of valid range" in str(ctx.exception)
        )

        # Port 0 (reserved / invalid for HTTP)
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://example.com:0", is_prod=True)
        self.assertIn("out of valid range", str(ctx.exception))

        # Negative port
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://example.com:-80", is_prod=True)
        self.assertTrue(
            "Port must be a valid integer" in str(ctx.exception) or
            "out of valid range" in str(ctx.exception)
        )

    def test_08l_malformed_hostnames_rejected(self):
        # Starts with hyphen
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://-bad.com", is_prod=True)
        self.assertIn("not a valid domain or IP address", str(ctx.exception))

        # Ends with hyphen
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://bad-.com", is_prod=True)
        self.assertIn("not a valid domain or IP address", str(ctx.exception))

        # Double dots (empty label)
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://ex..com", is_prod=True)
        self.assertIn("not a valid domain or IP address", str(ctx.exception))

        # Invalid characters in domain
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://exam$ple.com", is_prod=True)
        self.assertIn("not a valid domain or IP address", str(ctx.exception))

        # Invalid IPv6
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://[invalid::ipv6::]", is_prod=True)
        self.assertIn("not a valid domain or IP address", str(ctx.exception))

    def test_08m_control_characters_and_internal_whitespace_rejected(self):
        # Carriage return / newline
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://example.com\r\n", is_prod=True)
        self.assertIn("Control characters are not permitted", str(ctx.exception))

        # Null byte
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://example.com\x00", is_prod=True)
        self.assertIn("Control characters are not permitted", str(ctx.exception))

        # Tab character
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://example.com\t", is_prod=True)
        self.assertIn("Control characters are not permitted", str(ctx.exception))

        # Whitespace inside origin
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://exa mple.com", is_prod=True)
        self.assertIn("Whitespace within origin is not permitted", str(ctx.exception))

    def test_08n_sensitive_tokens_not_leaked_in_exceptions(self):
        secret_query_token = "SECRET_TOKEN_XYZ_98765"
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins(f"https://example.com?auth={secret_query_token}", is_prod=True)
        self.assertIn("Origin must not include query parameters", str(ctx.exception))
        self.assertNotIn(secret_query_token, str(ctx.exception))

        secret_fragment_hash = "SECRET_FRAGMENT_HASH_4321"
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins(f"https://example.com#{secret_fragment_hash}", is_prod=True)
        self.assertIn("Origin must not include a fragment", str(ctx.exception))
        self.assertNotIn(secret_fragment_hash, str(ctx.exception))

    def test_08o_multiple_simultaneous_errors_sentinel_redaction(self):
        sentinel_user = "UNIQUE_USER_ALPHA_111"
        sentinel_pass = "UNIQUE_PASS_BRAVO_222"
        sentinel_query = "UNIQUE_QUERY_CHARLIE_333"
        sentinel_frag = "UNIQUE_FRAG_DELTA_444"
        sentinel_path = "UNIQUE_PATH_ECHO_555"
        sentinel_host = "UNIQUE_HOST_FOXTROT_666"

        all_sentinels = [
            sentinel_user, sentinel_pass, sentinel_query,
            sentinel_frag, sentinel_path, sentinel_host
        ]

        def assert_no_sentinel_leaked(exception_text):
            for s in all_sentinels:
                self.assertNotIn(s, exception_text)

        # Case 1: Invalid scheme + sensitive query token + sensitive path
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins(f"ftp://example.com/{sentinel_path}?token={sentinel_query}", is_prod=True)
        assert_no_sentinel_leaked(str(ctx.exception))

        # Case 2: Malformed hostname + sensitive path + sensitive query + sensitive fragment
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins(
                f"https://-bad-{sentinel_host}.com/{sentinel_path}?api_key={sentinel_query}#{sentinel_frag}",
                is_prod=True
            )
        assert_no_sentinel_leaked(str(ctx.exception))

        # Case 3: Out-of-range port + sensitive path + sensitive fragment
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins(
                f"https://example.com:70000/{sentinel_path}#{sentinel_frag}",
                is_prod=True
            )
        assert_no_sentinel_leaked(str(ctx.exception))

        # Case 4: Non-integer port + sensitive path
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins(
                f"https://example.com:bad_port_{sentinel_host}/{sentinel_path}",
                is_prod=True
            )
        assert_no_sentinel_leaked(str(ctx.exception))

        # Case 5: Embedded credentials + invalid scheme + bad port + path + query + fragment (ALL ERRORS SIMULTANEOUSLY)
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins(
                f"ftp://{sentinel_user}:{sentinel_pass}@-bad-{sentinel_host}.com:99999/{sentinel_path}?q={sentinel_query}#{sentinel_frag}",
                is_prod=True
            )
        assert_no_sentinel_leaked(str(ctx.exception))

        # Case 6: Control character + sensitive path
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins(f"https://example.com/{sentinel_path}\r\n", is_prod=True)
        assert_no_sentinel_leaked(str(ctx.exception))

    # -------------------------------------------------------------------------
    # 9. Wildcard origins are rejected in production
    # -------------------------------------------------------------------------
    def test_09_wildcard_origins_rejected_in_production(self):
        # Direct function tests
        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("*", is_prod=True)
        self.assertIn("Wildcard '*' is not permitted", str(ctx.exception))

        with self.assertRaises(RuntimeError) as ctx:
            parse_allowed_origins("https://app.render.com, *", is_prod=True)
        self.assertIn("Wildcard '*' is not permitted", str(ctx.exception))

        # Config reload test
        with patch.dict(os.environ, {
            'FLASK_ENV': 'production',
            'SECRET_KEY': 'prod-secret-key-12345',
            'DATABASE_URL': 'postgresql://localhost/db',
            'ALLOWED_ORIGINS': '*'
        }, clear=False):
            with self.assertRaises(RuntimeError) as ctx:
                importlib.reload(config)
            self.assertIn("Wildcard '*' is not permitted", str(ctx.exception))

        # create_app rejection test
        class InsecureConfig(config.Config):
            CORS_ALLOWED_ORIGINS = '*'

        with patch.dict(os.environ, {
            'FLASK_ENV': 'production',
            'SECRET_KEY': 'prod-secret-key-12345',
            'DATABASE_URL': 'postgresql://localhost/db',
            'ALLOWED_ORIGINS': 'https://app.render.com'
        }, clear=False):
            importlib.reload(config)
            from app import create_app
            with self.assertRaises(RuntimeError) as ctx:
                create_app(InsecureConfig)
            self.assertIn("Wildcard '*' is not permitted", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 10. Development mode retains intended local defaults
    # -------------------------------------------------------------------------
    def test_10_development_mode_retains_intended_local_defaults(self):
        # Unset / clean environment simulates local dev
        clean_dev = {
            'FLASK_ENV': 'development',
            'ENV': '',
            'RENDER': '',
            'SECRET_KEY': '',
            'DATABASE_URL': '',
            'ALLOWED_ORIGINS': ''
        }
        with patch.dict(os.environ, clean_dev, clear=False):
            if 'RENDER' in os.environ:
                del os.environ['RENDER']
            if 'ENV' in os.environ:
                del os.environ['ENV']
            importlib.reload(config)
            self.assertFalse(is_production())
            self.assertEqual(config.Config.SECRET_KEY, 'dev-insecure-key-set-SECRET_KEY-in-production')
            self.assertTrue(config.Config.SQLALCHEMY_DATABASE_URI.startswith('sqlite:///'))
            self.assertEqual(config.Config.CORS_ALLOWED_ORIGINS, "*")

        # Dev mode with explicit origins in .env
        dev_origins = parse_allowed_origins("http://localhost:5000, http://127.0.0.1:5000", is_prod=False)
        self.assertEqual(dev_origins, ["http://localhost:5000", "http://127.0.0.1:5000"])

    # -------------------------------------------------------------------------
    # 11. PostgreSQL URL normalization remains functional
    # -------------------------------------------------------------------------
    def test_11_postgresql_url_normalization(self):
        with patch.dict(os.environ, {
            'FLASK_ENV': 'production',
            'SECRET_KEY': 'prod-secret-key-12345',
            'DATABASE_URL': 'postgres://supabase_user:securepass@db.host.supabase.co:5432/postgres',
            'ALLOWED_ORIGINS': 'https://skillxchange.onrender.com'
        }, clear=False):
            importlib.reload(config)
            self.assertTrue(config.Config.SQLALCHEMY_DATABASE_URI.startswith('postgresql://'))
            self.assertIn('supabase_user:securepass@db.host.supabase.co:5432/postgres', config.Config.SQLALCHEMY_DATABASE_URI)

    # -------------------------------------------------------------------------
    # 12. Scheduler API disabled and endpoints inaccessible
    # -------------------------------------------------------------------------
    def test_12_scheduler_api_disabled_and_endpoints_inaccessible(self):
        self.assertFalse(config.Config.SCHEDULER_API_ENABLED)
        from app import create_app, scheduler
        app = create_app(config.Config)

        # Verify no scheduler management routes are registered in app.url_map
        scheduler_rules = [r.rule for r in app.url_map.iter_rules() if r.rule.startswith('/scheduler')]
        self.assertEqual(scheduler_rules, [])

        # Verify client receives 404 on scheduler management endpoints
        client = app.test_client()
        for endpoint in ['/scheduler/jobs', '/scheduler/pause', '/scheduler/shutdown', '/scheduler']:
            res_get = client.get(endpoint)
            self.assertEqual(res_get.status_code, 404)
            res_post = client.post(endpoint)
            self.assertEqual(res_post.status_code, 404)

        # Verify internal scheduling functionality remains intact
        def dummy_task():
            pass

        scheduler.add_job(
            id='internal_test_reminder',
            func=dummy_task,
            trigger='date',
            run_date='2099-01-01 00:00:00',
            replace_existing=True
        )
        self.assertIsNotNone(scheduler.get_job('internal_test_reminder'))
        scheduler.remove_job('internal_test_reminder')
        self.assertIsNone(scheduler.get_job('internal_test_reminder'))


if __name__ == '__main__':
    unittest.main()
