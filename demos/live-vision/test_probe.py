import copy
import unittest

import probe


def response():
    return {
        "answers": {
            "red_present": {"type": "noul", "noul": 0.99},
            "red_position": {
                "type": "choice", "choice": "left",
                "probabilities": {"left": 0.98, "right": 0.01, "absent": 0.01},
            },
            "red_shape": {
                "type": "choice", "choice": "circle",
                "probabilities": {"circle": 0.98, "square": 0.01, "absent": 0.01},
            },
        },
    }


class ProbeTests(unittest.TestCase):
    def test_valid_response_does_not_make_wrong_scene_pass(self):
        payload = response()
        self.assertTrue(all(probe.inspect_answers(payload, "red-circle-left").values()))
        checks = probe.inspect_answers(payload, "red-square-right")
        self.assertTrue(checks["red_present"])
        self.assertFalse(checks["red_position"])
        self.assertFalse(checks["red_shape"])

    def test_bad_answers_fail_instead_of_becoming_success(self):
        variants = []
        missing = response()
        del missing["answers"]["red_shape"]
        variants.append(missing)
        unsupported = response()
        unsupported["answers"]["red_shape"]["choice"] = "triangle"
        variants.append(unsupported)
        distribution = response()
        distribution["answers"]["red_position"]["probabilities"]["left"] = 0.1
        variants.append(distribution)
        for value in (True, float("nan"), -0.1, 1.1, "0.9"):
            invalid = response()
            invalid["answers"]["red_present"]["noul"] = value
            variants.append(invalid)
        for payload in variants:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                probe.inspect_answers(payload, "red-circle-left")

    def test_counterfactual_requests_differ_only_in_pixels(self):
        bodies = [
            probe.request_body("test-deployment", probe.image_png(scene))
            for scene in probe.SCENES
        ]
        encoded_images = {body["assets"]["frame.png"]["data_base64"] for body in bodies}
        self.assertEqual(len(encoded_images), 3)
        without_pixels = []
        for body in bodies:
            body = copy.deepcopy(body)
            del body["assets"]["frame.png"]["data_base64"]
            without_pixels.append(body)
        self.assertEqual(without_pixels[0], without_pixels[1])
        self.assertEqual(without_pixels[1], without_pixels[2])


if __name__ == "__main__":
    unittest.main()
