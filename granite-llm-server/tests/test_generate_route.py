import unittest
from app.main import app as flask_app

# To run tests use below command while in granite-llm-server dir
# python -m unittest tests.test_generate_route -v

class TestGenerateRoute(unittest.TestCase):
    def test_generate_sends_exact_payload_to_ollama(self):
        client = flask_app.test_client()
        