import unittest
from app.request_parser import extract_generation_options, MAX_OUTPUT_TOKENS

# To run tests use below command while in granite-llm-server dir
# python -m unittest discover -s tests -p "test_*.py" -v

class TestGenerationOptions(unittest.TestCase):

    def test_extracts_and_maps_valid_generation_options(self):
        payload = {
            "max_output_tokens": 500,
            "temperature": 0.7,
            "top_p": 0.9,
        }

        result = extract_generation_options(payload)

        expected = {
            "num_predict": 500,
            "temperature": 0.7,
            "top_p": 0.9,
        }

        self.assertEqual(result, expected)

    def test_returns_empty_options_when_parameters_are_omitted(self):
        payload = {}

        result = extract_generation_options(payload)

        expected = {}

        self.assertEqual(result, expected)

    # Min and Max tests for max_output_tokens
    def test_rejects_max_output_tokens_below_minimum(self):
        payload = {
            "max_output_tokens": 0,
            "temperature": 0.7,
            "top_p": 0.9,
        }

        with self.assertRaisesRegex(ValueError, "max_output_tokens"):
            extract_generation_options(payload)

    def test_rejects_max_output_tokens_above_maximum(self):
        payload = {
            "max_output_tokens": MAX_OUTPUT_TOKENS + 1,
            "temperature": 0.7,
            "top_p": 0.9,
        }

        with self.assertRaisesRegex(ValueError, "max_output_tokens"):
            extract_generation_options(payload)

    def test_returns_max_output_tokens_at_minimum(self):
        payload = {
            "max_output_tokens": 1,
            "temperature": 0.7,
            "top_p": 0.9,
        }

        result = extract_generation_options(payload)

        expected = {
            "num_predict": 1,
            "temperature": 0.7,
            "top_p": 0.9,
        }

        self.assertEqual(result, expected)
    
    def test_returns_max_output_tokens_at_maximum(self):
        payload = {
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "temperature": 0.7,
            "top_p": 0.9,
        }

        result = extract_generation_options(payload)

        expected = {
            "num_predict": MAX_OUTPUT_TOKENS,
            "temperature": 0.7,
            "top_p": 0.9,
        }

        self.assertEqual(result, expected)

    # Min and Max tests for temperature
    def test_rejects_temperature_below_minimum(self):
        payload = {
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "temperature": -1,
            "top_p": 0.9,
        }

        with self.assertRaisesRegex(ValueError, "temperature"):
            extract_generation_options(payload)

    def test_rejects_temperature_above_maximum(self):
        payload = {
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "temperature": 3,
            "top_p": 0.9,
        }

        with self.assertRaisesRegex(ValueError, "temperature"):
            extract_generation_options(payload)

    def test_returns_temperature_at_minimum(self):
        payload = {
            "max_output_tokens": 1,
            "temperature": 0,
            "top_p": 0.9,
        }

        result = extract_generation_options(payload)

        expected = {
            "num_predict": 1,
            "temperature": 0,
            "top_p": 0.9,
        }

        self.assertEqual(result, expected)
    
    def test_returns_temperature_at_maximum(self):
        payload = {
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "temperature": 2,
            "top_p": 0.9,
        }

        result = extract_generation_options(payload)

        expected = {
            "num_predict": MAX_OUTPUT_TOKENS,
            "temperature": 2,
            "top_p": 0.9,
        }

        self.assertEqual(result, expected)

    # Min and Max tests for top_p
    def test_rejects_top_p_below_minimum(self):
        payload = {
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "temperature": 0.7,
            "top_p": -1,
        }

        with self.assertRaisesRegex(ValueError, "top_p"):
            extract_generation_options(payload)

    def test_rejects_top_p_above_maximum(self):
        payload = {
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "temperature": 0.7,
            "top_p": 2,
        }

        with self.assertRaisesRegex(ValueError, "top_p"):
            extract_generation_options(payload)

    def test_returns_top_p_at_minimum(self):
        payload = {
            "max_output_tokens": 1,
            "temperature": 0.7,
            "top_p": 0,
        }

        result = extract_generation_options(payload)

        expected = {
            "num_predict": 1,
            "temperature": 0.7,
            "top_p": 0,
        }

        self.assertEqual(result, expected)
    
    def test_returns_top_p_at_maximum(self):
        payload = {
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "temperature": 0.7,
            "top_p": 1,
        }

        result = extract_generation_options(payload)

        expected = {
            "num_predict": MAX_OUTPUT_TOKENS,
            "temperature": 0.7,
            "top_p": 1,
        }

        self.assertEqual(result, expected)

    # Boolean rejection tests for max_output_tokens
    def test_rejects_max_output_tokens_when_false(self):
        payload = {
            "max_output_tokens": False,
            "temperature": 0.7,
            "top_p": 0.9,
        }

        with self.assertRaisesRegex(ValueError, "max_output_tokens"):
            extract_generation_options(payload)
    
    def test_rejects_max_output_tokens_when_true(self):
        payload = {
            "max_output_tokens": True,
            "temperature": 0.7,
            "top_p": 0.9,
        }

        with self.assertRaisesRegex(ValueError, "max_output_tokens"):
            extract_generation_options(payload)

    # Boolean rejection tests for temperature
    def test_rejects_temperature_when_false(self):
        payload = {
            "max_output_tokens": 400,
            "temperature": False,
            "top_p": 0.9,
        }

        with self.assertRaisesRegex(ValueError, "temperature"):
            extract_generation_options(payload)
    
    def test_rejects_temperature_when_true(self):
        payload = {
            "max_output_tokens": 400,
            "temperature": True,
            "top_p": 0.9,
        }

        with self.assertRaisesRegex(ValueError, "temperature"):
            extract_generation_options(payload)

    # Boolean rejection tests for top_p
    def test_rejects_top_p_when_false(self):
        payload = {
            "max_output_tokens": 400,
            "temperature": 0.7,
            "top_p": False,
        }

        with self.assertRaisesRegex(ValueError, "top_p"):
            extract_generation_options(payload)
    
    def test_rejects_top_p_when_true(self):
        payload = {
            "max_output_tokens": 400,
            "temperature": 0.7,
            "top_p": True,
        }

        with self.assertRaisesRegex(ValueError, "top_p"):
            extract_generation_options(payload)


    # max_output_tokens tests
    def test_rejects_max_output_tokens_when_float(self):
        payload = {
            "max_output_tokens": 500.0
        }

        with self.assertRaisesRegex(ValueError, "max_output_tokens"):
            extract_generation_options(payload)

    def test_rejects_max_output_tokens_when_string(self):
        payload = {
            "max_output_tokens": "500"
        }

        with self.assertRaisesRegex(ValueError, "max_output_tokens"):
            extract_generation_options(payload)

    def test_rejects_max_output_tokens_when_none(self):
        payload = {
            "max_output_tokens": None
        }

        with self.assertRaisesRegex(ValueError, "max_output_tokens"):
            extract_generation_options(payload)
    
    #temperature tests
    def test_rejects_temperature_when_string(self):
        payload = {
            "temperature": "0.7"
        }

        with self.assertRaisesRegex(ValueError, "temperature"):
            extract_generation_options(payload)

    def test_rejects_temperature_when_none(self):
        payload = {
            "temperature": None
        }

        with self.assertRaisesRegex(ValueError, "temperature"):
            extract_generation_options(payload)

    def test_rejects_temperature_when_nan(self):
        payload = {
            "temperature": float("nan")
        }

        with self.assertRaisesRegex(ValueError, "temperature"):
            extract_generation_options(payload)
    
    def test_rejects_temperature_when_positive_infinity(self):
        payload = {
            "temperature": float("inf")
        }

        with self.assertRaisesRegex(ValueError, "temperature"):
            extract_generation_options(payload)

    def test_rejects_temperature_when_negative_infinity(self):
        payload = {
           "temperature": float("-inf")
        }

        with self.assertRaisesRegex(ValueError, "temperature"):
            extract_generation_options(payload)

    def test_returns_only_temperature_when_only_temperature_is_provided(self):
        payload = {
            "temperature": 0.7
        }

        result = extract_generation_options(payload)

        expected = {
            "temperature": 0.7
        }

        self.assertEqual(result, expected)

    #top_p tests
    def test_rejects_top_p_when_string(self):
        payload = {
           "top_p": "0.9"
        }

        with self.assertRaisesRegex(ValueError, "top_p"):
            extract_generation_options(payload)

    def test_rejects_top_p_when_none(self):
        payload = {
           "top_p": None
        }

        with self.assertRaisesRegex(ValueError, "top_p"):
            extract_generation_options(payload)
    
    def test_rejects_top_p_when_nan(self):
        payload = {
           "top_p": float("nan")
        }

        with self.assertRaisesRegex(ValueError, "top_p"):
            extract_generation_options(payload)
    
    def test_rejects_top_p_when_positive_infinity(self):
        payload = {
           "top_p": float("inf")
        }

        with self.assertRaisesRegex(ValueError, "top_p"):
            extract_generation_options(payload)
    
    def test_rejects_top_p_when_negative_infinity(self):
        payload = {
           "top_p": float("-inf")
        }

        with self.assertRaisesRegex(ValueError, "top_p"):
            extract_generation_options(payload)

