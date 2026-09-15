import unittest

from pydantic import ValidationError

from its_multi_agent.backend.app.infrastructure.maps.coordinates import (
    is_in_china,
    to_bd09ll,
    wgs84_to_gcj02,
)
from its_multi_agent.backend.app.infrastructure.maps.origin import (
    device_origin_payload,
    normalize_explicit_address,
)
from its_multi_agent.backend.app.schemas.request import ChatMessageRequest, GeoLocation


class CoordinateConversionTest(unittest.TestCase):
    def test_beijing_wgs84_converts_to_baidu_coordinates(self):
        longitude, latitude = to_bd09ll(116.397389, 39.908722, "wgs84")
        self.assertAlmostEqual(longitude, 116.410, delta=0.01)
        self.assertAlmostEqual(latitude, 39.916, delta=0.01)

    def test_gcj_offset_is_not_applied_outside_china(self):
        self.assertFalse(is_in_china(-0.1276, 51.5072))
        self.assertEqual(wgs84_to_gcj02(-0.1276, 51.5072), (-0.1276, 51.5072))

    def test_bd09_coordinates_are_not_converted_twice(self):
        self.assertEqual(to_bd09ll(116.41, 39.92, "bd09ll"), (116.41, 39.92))


class OriginRulesTest(unittest.TestCase):
    def test_relative_location_is_never_geocoded(self):
        for text in ("附近的维修点", "从当前位置去杭州西湖", "我这里有哪些商场"):
            with self.subTest(text=text):
                self.assertEqual(normalize_explicit_address(text), "")

    def test_explicit_origin_is_kept(self):
        self.assertEqual(normalize_explicit_address(" 上海虹桥站 "), "上海虹桥站")

    def test_device_payload_is_bd09ll_and_keeps_accuracy(self):
        payload = device_origin_payload(GeoLocation(
            latitude=39.908722,
            longitude=116.397389,
            accuracy=18.5,
            coordinate_system="wgs84",
        ))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["source"], "device")
        self.assertEqual(payload["coordinate_system"], "bd09ll")
        self.assertEqual(payload["accuracy_meters"], 18.5)


class LocationRequestValidationTest(unittest.TestCase):
    def test_chat_request_accepts_structured_origin(self):
        request = ChatMessageRequest.model_validate({
            "query": "从当前位置去故宫",
            "context": {"session_id": "session_1"},
            "origin": {
                "latitude": 39.9,
                "longitude": 116.4,
                "accuracy": 20,
                "coordinate_system": "wgs84",
                "captured_at": 1700000000000,
            },
        })
        self.assertEqual(request.origin.coordinate_system, "wgs84")

    def test_invalid_coordinates_are_rejected(self):
        with self.assertRaises(ValidationError):
            GeoLocation(latitude=100, longitude=116.4)


if __name__ == "__main__":
    unittest.main()
