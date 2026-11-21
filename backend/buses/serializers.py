import math
from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

MAX_SPEED_KMH = 120.0
MAX_FUTURE_SKEW = timedelta(minutes=5)


class IngestSerializer(serializers.Serializer):
    bus_id = serializers.CharField(max_length=20)
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)
    speed = serializers.FloatField(min_value=0, max_value=MAX_SPEED_KMH, required=False, default=0.0)
    heading = serializers.FloatField(min_value=0, max_value=360, required=False, default=0.0)
    fix_time = serializers.DateTimeField(required=False, allow_null=True, default=None)

    def validate_fix_time(self, value):
        if value and value > timezone.now() + MAX_FUTURE_SKEW:
            raise serializers.ValidationError("fix_time is in the future.")
        return value

    def validate(self, attrs):
        # NaN/Infinity slip through min/max comparisons, so reject them explicitly.
        for name in ("lat", "lng", "speed", "heading"):
            if not math.isfinite(attrs[name]):
                raise serializers.ValidationError({name: "Must be a finite number."})
        return attrs