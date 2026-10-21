import pytest
from app.routes.auth import classify_db_exception

class MockOrig(Exception):
    def __init__(self, msg, pgcode=None):
        super().__init__(msg)
        self.pgcode = pgcode

class MockDBAPIError(Exception):
    def __init__(self, orig):
        self.orig = orig

def test_dns_resolution_failure():
    exc = MockDBAPIError(MockOrig('could not translate host name "Skill@aws-0-ap-southeast-2.pooler.supabase.com" to address'))
    assert classify_db_exception(exc) == "DNS_RESOLUTION_FAILURE"

def test_auth_password_failure_via_pgcode_28P01():
    exc = MockDBAPIError(MockOrig('password authentication failed', pgcode='28P01'))
    assert classify_db_exception(exc) == "AUTH_PASSWORD_FAILURE (SQLSTATE 28P01)"

def test_auth_specification_failure_via_pgcode_28000():
    exc = MockDBAPIError(MockOrig('invalid authorization specification', pgcode='28000'))
    assert classify_db_exception(exc) == "AUTH_SPECIFICATION_FAILURE (SQLSTATE 28000)"

def test_auth_other_failure_via_pgcode():
    exc = MockDBAPIError(MockOrig('some other auth error', pgcode='28006'))
    assert classify_db_exception(exc) == "AUTH_OTHER_FAILURE (SQLSTATE 28006)"

def test_auth_password_failure_via_message():
    exc = MockDBAPIError(MockOrig('FATAL: password authentication failed for user "postgres"'))
    assert classify_db_exception(exc) == "AUTH_PASSWORD_FAILURE (SQLSTATE 28P01)"

def test_connection_timeout():
    exc = MockDBAPIError(MockOrig('could not connect to server: Connection timed out'))
    assert classify_db_exception(exc) == "CONNECTION_TIMEOUT_OR_REFUSED"

def test_ssl_failure():
    exc = MockDBAPIError(MockOrig('SSL SYSCALL error: EOF detected'))
    assert classify_db_exception(exc) == "SSL_TLS_FAILURE"

def test_tenant_not_found():
    exc = MockDBAPIError(MockOrig('FATAL: tenant blvpsauevioudmnigvzc not found'))
    assert classify_db_exception(exc) == "TENANT_NOT_FOUND"

def test_other_operational_error():
    exc = MockDBAPIError(MockOrig('unexpected EOF on client connection'))
    assert classify_db_exception(exc) == "OTHER_OPERATIONAL_ERROR (MockOrig)"

def test_zero_credential_leakage():
    sensitive_token = "SUPER_SECRET_RAW_PASSWORD_98765"
    exc = MockDBAPIError(MockOrig(f'FATAL: password authentication failed for user with {sensitive_token}'))
    result = classify_db_exception(exc)
    assert sensitive_token not in result
    assert result == "AUTH_PASSWORD_FAILURE (SQLSTATE 28P01)"
