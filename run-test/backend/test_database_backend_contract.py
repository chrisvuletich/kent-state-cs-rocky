from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
API_ROCKY_DIR = ROOT / "api-rocky"
BACKEND_DIR = ROOT / "rocky-backend"
sys.path.insert(0, str(API_ROCKY_DIR))
sys.path.insert(0, str(BACKEND_DIR))

from backend.config import Settings
from backend import storage


API_SPEC = importlib.util.spec_from_file_location(
    "api_rocky_database_contract", API_ROCKY_DIR / "api.py"
)
if API_SPEC is None or API_SPEC.loader is None:
    raise RuntimeError("Unable to load api-rocky for database contract tests.")

api_rocky = importlib.util.module_from_spec(API_SPEC)
with patch.dict(
    os.environ,
    {
        "ROCKY_APP_ENV": "test",
        "ROCKY_TEST_SKIP_DATABASE_INIT": "true",
    },
):
    API_SPEC.loader.exec_module(api_rocky)


class FakeCollection:
    def create_index(self, keys, **options):
        return "synthetic-index"


class FakeDatabase:
    def __init__(self):
        self.collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str):
        return self.collections.setdefault(name, FakeCollection())


class FakeMongoClient:
    def __init__(self):
        self.databases: dict[str, FakeDatabase] = {}

    def __getitem__(self, name: str):
        return self.databases.setdefault(name, FakeDatabase())


def settings_for(*, app_env: str, db_backend: str, mongodb_uri: str) -> Settings:
    return Settings(
        app_env=app_env,
        host="127.0.0.1",
        port=5001,
        debug=False,
        db_backend=db_backend,
        mongodb_uri=mongodb_uri,
        db_name="synthetic_test_database",
        enable_db_inspector=False,
        enable_preview_login=False,
        enable_microsoft_oauth=True,
    )


class DatabaseBackendContractTests(unittest.TestCase):
    def test_api_database_skip_defaults_to_disabled(self):
        with patch.dict(
            os.environ,
            {"ROCKY_TEST_SKIP_DATABASE_INIT": "false"},
        ):
            self.assertFalse(
                api_rocky.should_skip_database_initialization_for_tests()
            )

    def test_api_database_skip_rejects_non_test_environment(self):
        with patch.dict(
            os.environ,
            {
                "ROCKY_APP_ENV": "production",
                "ROCKY_TEST_SKIP_DATABASE_INIT": "true",
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "ROCKY_APP_ENV=test"):
                api_rocky.should_skip_database_initialization_for_tests()

    def test_production_cannot_select_mongita_when_mongodb_is_configured(self):
        configured = settings_for(
            app_env="production",
            db_backend="mongita",
            mongodb_uri="synthetic-mongodb-target",
        )

        with (
            patch.object(storage, "MongoClient", return_value=FakeMongoClient()),
            patch.object(storage, "MongitaClientDisk") as mongita_client,
        ):
            collections = storage.build_collections(configured)

        self.assertIsNotNone(collections.api_keys)
        mongita_client.assert_not_called()

    @unittest.expectedFailure
    def test_unknown_backend_selector_fails_clearly(self):
        configured = settings_for(
            app_env="development",
            db_backend="unknown",
            mongodb_uri="",
        )

        with (
            patch.object(
                storage,
                "MongitaClientDisk",
                return_value=FakeMongoClient(),
            ),
            self.assertRaises(RuntimeError),
        ):
            storage.build_collections(configured)

    def test_backend_mongodb_failure_never_falls_back_to_mongita(self):
        configured = settings_for(
            app_env="production",
            db_backend="mongodb",
            mongodb_uri="synthetic-mongodb-target",
        )

        with (
            patch.object(storage, "MongoClient", side_effect=RuntimeError),
            patch.object(storage, "MongitaClientDisk") as mongita_client,
            self.assertRaises(RuntimeError),
        ):
            storage.build_collections(configured)

        mongita_client.assert_not_called()

    def test_api_unknown_backend_selector_fails_clearly(self):
        original_backend = api_rocky.DB_BACKEND
        api_rocky.DB_BACKEND = "unknown"
        try:
            with self.assertRaises(RuntimeError):
                api_rocky.initialize_database()
        finally:
            api_rocky.DB_BACKEND = original_backend

    def test_api_mongodb_failure_never_falls_back_to_mongita(self):
        original_values = (
            api_rocky.DB_BACKEND,
            api_rocky.MONGODB_CONNECT_ATTEMPTS,
            api_rocky.MONGODB_RETRY_SECONDS,
        )
        api_rocky.DB_BACKEND = "mongodb"
        api_rocky.MONGODB_CONNECT_ATTEMPTS = 1
        api_rocky.MONGODB_RETRY_SECONDS = 0
        try:
            with (
                patch.object(
                    api_rocky,
                    "MongoClient",
                    side_effect=api_rocky.PyMongoError,
                ),
                patch.object(api_rocky, "MongitaClientDisk") as mongita_client,
                self.assertRaises(RuntimeError),
            ):
                api_rocky.initialize_database()
            mongita_client.assert_not_called()
        finally:
            (
                api_rocky.DB_BACKEND,
                api_rocky.MONGODB_CONNECT_ATTEMPTS,
                api_rocky.MONGODB_RETRY_SECONDS,
            ) = original_values


if __name__ == "__main__":
    unittest.main()
