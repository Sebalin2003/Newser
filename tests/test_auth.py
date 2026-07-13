from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from src import auth


class AuthTokenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public_key = cls.private_key.public_key()

    def token(self, **overrides) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "user-123",
            "email": "reader@example.com",
            "user_metadata": {"full_name": "Technical Reader"},
            "aud": "authenticated",
            "iss": "https://project.supabase.co/auth/v1",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        }
        payload.update(overrides)
        return jwt.encode(payload, self.private_key, algorithm="RS256", headers={"kid": "test-key"})

    def validate(self, token: str):
        signing_key = type("SigningKey", (), {"key": self.public_key})()
        client = type("JwksClient", (), {"get_signing_key_from_jwt": lambda _self, _token: signing_key})()
        with patch.dict(os.environ, {"SUPABASE_URL": "https://project.supabase.co"}), \
             patch.object(auth, "_jwks_client", return_value=client):
            return auth.validate_access_token(token)

    def test_valid_token_uses_full_name(self) -> None:
        user = self.validate(self.token())

        self.assertEqual(user.id, "user-123")
        self.assertEqual(user.name, "Technical Reader")
        self.assertEqual(user.email, "reader@example.com")

    def test_name_falls_back_to_provider_name_then_email(self) -> None:
        provider_name = self.validate(self.token(user_metadata={"name": "Provider Name"}))
        email_name = self.validate(self.token(user_metadata={}))

        self.assertEqual(provider_name.name, "Provider Name")
        self.assertEqual(email_name.name, "reader@example.com")

    def test_expired_wrong_audience_and_wrong_issuer_are_rejected(self) -> None:
        now = datetime.now(timezone.utc)
        tokens = [
            self.token(exp=now - timedelta(seconds=1)),
            self.token(aud="other"),
            self.token(iss="https://other.example/auth/v1"),
        ]

        for token in tokens:
            with self.subTest(token=token[-12:]), self.assertRaises(HTTPException) as raised:
                self.validate(token)
            self.assertEqual(raised.exception.status_code, 401)

    def test_malformed_token_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            self.validate("not-a-jwt")

        self.assertEqual(raised.exception.status_code, 401)

    def test_missing_supabase_url_reports_auth_not_configured(self) -> None:
        with patch.dict(os.environ, {"SUPABASE_URL": ""}), self.assertRaises(HTTPException) as raised:
            auth.validate_access_token("token")

        self.assertEqual(raised.exception.status_code, 503)

    def test_supabase_userinfo_fallback_when_jwks_validation_fails(self) -> None:
        response = type("Response", (), {
            "status_code": 200,
            "json": lambda _self: {
                "id": "user-from-supabase",
                "email": "reader@example.com",
                "user_metadata": {"full_name": "Supabase Reader"},
            },
        })()

        with patch.dict(os.environ, {
            "SUPABASE_URL": "https://project.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "publishable-key",
        }), \
             patch.object(auth, "_jwks_client", side_effect=jwt.PyJWTError("unsupported algorithm")), \
             patch.object(auth.requests, "get", return_value=response) as get:
            user = auth.validate_access_token("token")

        self.assertEqual(user.id, "user-from-supabase")
        self.assertEqual(user.name, "Supabase Reader")
        get.assert_called_once()

    def test_supabase_userinfo_fallback_rejects_non_200_response(self) -> None:
        response = type("Response", (), {"status_code": 401})()

        with patch.dict(os.environ, {
            "SUPABASE_URL": "https://project.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "publishable-key",
        }), \
             patch.object(auth, "_jwks_client", side_effect=jwt.PyJWTError("unsupported algorithm")), \
             patch.object(auth.requests, "get", return_value=response), \
             self.assertRaises(HTTPException) as raised:
            auth.validate_access_token("token")

        self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
