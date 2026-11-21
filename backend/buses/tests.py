from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import Bus, Position, Route

KEY = "test-key-123"


class IngestTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        route = Route.objects.create(name="Test", path=[[24.0, 90.42], [23.95, 90.41], [23.879, 90.4005]])
        Bus.objects.create(code="BUS-01", route=route, api_key=KEY)

    def post(self, overrides=None, key=KEY):
        body = {"bus_id": "BUS-01", "lat": 23.95, "lng": 90.41, "speed": 20, "heading": 90}
        body.update(overrides or {})
        extra = {"HTTP_X_API_KEY": key} if key is not None else {}
        return self.client.post(reverse("ingest"), body, format="json", **extra)

    # --- the 3 required tests ---
    def test_valid_post_is_stored(self):
        res = self.post({"fix_time": timezone.now().isoformat()})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Position.objects.count(), 1)
        self.assertIsNotNone(Position.objects.first().fix_time)

    def test_wrong_api_key_is_rejected(self):
        self.assertEqual(self.post(key="wrong-key").status_code, 401)
        self.assertEqual(self.post(key=None).status_code, 401)
        self.assertEqual(Position.objects.count(), 0)

    def test_out_of_range_coordinates_are_rejected(self):
        self.assertEqual(self.post({"lat": 91}).status_code, 400)
        self.assertEqual(self.post({"lng": -181}).status_code, 400)
        self.assertEqual(Position.objects.count(), 0)

    # --- extras covering the other validation rules ---
    def test_speed_above_120_is_rejected(self):
        self.assertEqual(self.post({"speed": 150}).status_code, 400)

    def test_position_far_from_route_is_rejected(self):
        res = self.post({"lat": 23.78, "lng": 90.40})   # ~11 km south of Abdullahpur
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["error"], "off_route")