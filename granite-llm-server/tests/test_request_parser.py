import unittest
from app.request_parser import (
    MAX_IMAGE_OUTPUT_TOKENS,
    MAX_OUTPUT_TOKENS,
    extract_generation_options,
    extract_reasoning,
    extract_stream,
)

# To run tests use below command while in granite-llm-server dir
# python -m unittest discover -s tests -p "test_*.py" -v


class TestStream(unittest.TestCase):
    def test_stream_defaults_false_and_accepts_booleans(self):
        self.assertFalse(extract_stream({}))
        self.assertFalse(extract_stream({"stream": False}))
        self.assertTrue(extract_stream({"stream": True}))

    def test_stream_rejects_non_booleans(self):
        for value in (None, 0, 1, "true", [], {}):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValueError,
                "stream",
            ):
                extract_stream({"stream": value})

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

    def test_accepts_the_larger_image_output_token_limit_when_selected(self):
        result = extract_generation_options(
            {"max_output_tokens": MAX_IMAGE_OUTPUT_TOKENS},
            max_output_tokens=MAX_IMAGE_OUTPUT_TOKENS,
        )

        self.assertEqual(result, {"num_predict": MAX_IMAGE_OUTPUT_TOKENS})

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

        # frequency_penalty tests
    def test_returns_both_penalty_options_when_valid(self):
        payload = {
            "frequency_penalty": 0.5,
            "presence_penalty": 1.25
        }

        result = extract_generation_options(payload)

        expected = {
            "frequency_penalty": 0.5,
            "presence_penalty": 1.25
        }

        self.assertEqual(result, expected)

    def test_returns_only_frequency_penalty_when_only_frequency_is_provided(self):
        payload = {
            "frequency_penalty": 0.5
        }

        result = extract_generation_options(payload)

        expected = {
            "frequency_penalty": 0.5
        }

        self.assertEqual(result, expected)

    def test_accepts_frequency_penalty_boundaries(self):
        for value in (-2, 2):
            with self.subTest(value=value):
                result = extract_generation_options({
                    "frequency_penalty": value
                })

                self.assertEqual(
                    result,
                    {"frequency_penalty": value}
                )

    def test_rejects_frequency_penalty_outside_range(self):
        for value in (-2.01, 2.01):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    ValueError,
                    "frequency_penalty"
                ):
                    extract_generation_options({
                        "frequency_penalty": value
                    })

    def test_rejects_invalid_frequency_penalty_values(self):
        invalid_values = [
            True,
            False,
            "0.5",
            None,
            float("nan"),
            float("inf"),
            float("-inf")
        ]

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    ValueError,
                    "frequency_penalty"
                ):
                    extract_generation_options({
                        "frequency_penalty": value
                    })

    # presence_penalty tests
    def test_returns_only_presence_penalty_when_only_presence_is_provided(self):
        payload = {
            "presence_penalty": 0.75
        }

        result = extract_generation_options(payload)

        expected = {
            "presence_penalty": 0.75
        }

        self.assertEqual(result, expected)

    def test_accepts_presence_penalty_boundaries(self):
        for value in (-2, 2):
            with self.subTest(value=value):
                result = extract_generation_options({
                    "presence_penalty": value
                })

                self.assertEqual(
                    result,
                    {"presence_penalty": value}
                )

    def test_rejects_presence_penalty_outside_range(self):
        for value in (-2.01, 2.01):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    ValueError,
                    "presence_penalty"
                ):
                    extract_generation_options({
                        "presence_penalty": value
                    })

    def test_rejects_invalid_presence_penalty_values(self):
        invalid_values = [
            True,
            False,
            "0.5",
            None,
            float("nan"),
            float("inf"),
            float("-inf")
        ]

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    ValueError,
                    "presence_penalty"
                ):
                    extract_generation_options({
                        "presence_penalty": value
                    })

class TestReasoning(unittest.TestCase):

    def test_returns_none_when_reasoning_is_omitted(self):
        payload = {}

        result = extract_reasoning(payload)

        self.assertIsNone(result)

    def test_returns_valid_reasoning_configuration(self):
        payload = {
            "reasoning": {
                "effort": "medium",
                "summary": "detailed"
            }
        }

        result = extract_reasoning(payload)

        expected = {
            "effort": "medium",
            "summary": "detailed"
        }

        self.assertEqual(result, expected)

    def test_accepts_all_supported_reasoning_efforts(self):
        supported_efforts = [
            "low",
            "medium",
            "high",
            "max"
        ]

        for effort in supported_efforts:
            with self.subTest(effort=effort):
                payload = {
                    "reasoning": {
                        "effort": effort,
                        "summary": "detailed"
                    }
                }

                result = extract_reasoning(payload)

                expected = {
                    "effort": effort,
                    "summary": "detailed"
                }

                self.assertEqual(result, expected)

    def test_rejects_reasoning_when_not_dictionary(self):
        invalid_reasoning_values = [
            None,
            True,
            False,
            "medium",
            5,
            []
        ]

        for value in invalid_reasoning_values:
            with self.subTest(value=value):
                payload = {
                    "reasoning": value
                }

                with self.assertRaisesRegex(
                    ValueError,
                    "reasoning"
                ):
                    extract_reasoning(payload)

    def test_rejects_reasoning_when_effort_is_missing(self):
        payload = {
            "reasoning": {
                "summary": "detailed"
            }
        }

        with self.assertRaisesRegex(
            ValueError,
            "reasoning.effort"
        ):
            extract_reasoning(payload)

    def test_rejects_effort_when_not_string(self):
        invalid_effort_values = [
            None,
            True,
            False,
            5,
            [],
            {}
        ]

        for value in invalid_effort_values:
            with self.subTest(value=value):
                payload = {
                    "reasoning": {
                        "effort": value,
                        "summary": "detailed"
                    }
                }

                with self.assertRaisesRegex(
                    ValueError,
                    "reasoning.effort"
                ):
                    extract_reasoning(payload)

    def test_rejects_unsupported_effort(self):
        payload = {
            "reasoning": {
                "effort": "extreme",
                "summary": "detailed"
            }
        }

        with self.assertRaisesRegex(
            ValueError,
            "reasoning.effort"
        ):
            extract_reasoning(payload)

    def test_rejects_reasoning_when_summary_is_missing(self):
        payload = {
            "reasoning": {
                "effort": "medium"
            }
        }

        with self.assertRaisesRegex(
            ValueError,
            "reasoning.summary"
        ):
            extract_reasoning(payload)

    def test_rejects_summary_when_not_string(self):
        invalid_summary_values = [
            None,
            True,
            False,
            5,
            [],
            {}
        ]

        for value in invalid_summary_values:
            with self.subTest(value=value):
                payload = {
                    "reasoning": {
                        "effort": "medium",
                        "summary": value
                    }
                }

                with self.assertRaisesRegex(
                    ValueError,
                    "reasoning.summary"
                ):
                    extract_reasoning(payload)

    def test_rejects_unsupported_summary(self):
        payload = {
            "reasoning": {
                "effort": "medium",
                "summary": "brief"
            }
        }

        with self.assertRaisesRegex(
            ValueError,
            "reasoning.summary"
        ):
            extract_reasoning(payload)
