import unittest
from app.request_parser import extract_generation_options

class TestGenerationOptions(unittest.TestCase):

    def test_extracts_and_maps_valid_generation_options(self):
        payload = {
            max_output_tokens: 500,
            temperature: 0.7,
            top_p: 0.9,
        }

        result = extract_generation_options(payload)

        expected = {
            num_predict: 500,
            temperature: 0.7,
            top_p: 0.9,
        }

        self.assertEqual(result, expected)