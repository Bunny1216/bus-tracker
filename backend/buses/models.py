import secrets

from django.db import models


def generate_api_key() -> str:
    return secrets.token_urlsafe(24)


class Route(models.Model):
    name = models.CharField(max_length=100)
    path = models.JSONField(default=list)   # [[lat, lng], ...]

    def __str__(self):
        return self.name


class Stop(models.Model):
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="stops")
    code = models.CharField(max_length=10, blank=True)   # e.g. "S1" from stops.json
    name = models.CharField(max_length=100)
    lat = models.FloatField()
    lng = models.FloatField()
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.order}. {self.name}"


class Bus(models.Model):
    code = models.CharField(max_length=20, unique=True)   # e.g. BUS-01
    route = models.ForeignKey(Route, null=True, blank=True, on_delete=models.SET_NULL, related_name="buses")
    api_key = models.CharField(max_length=64, default=generate_api_key)

    def __str__(self):
        return self.code


class Position(models.Model):
    bus = models.ForeignKey(Bus, on_delete=models.CASCADE, related_name="positions")
    lat = models.FloatField()
    lng = models.FloatField()
    speed = models.FloatField(default=0)      # km/h
    heading = models.FloatField(default=0)    # degrees
    fix_time = models.DateTimeField(null=True, blank=True)   # when the GPS fix was taken (device, UTC)
    received_at = models.DateTimeField(auto_now_add=True)    # when the server stored it

    class Meta:
        ordering = ["-received_at"]
        indexes = [models.Index(fields=["bus", "-received_at"], name="pos_bus_received_idx")]

    @property
    def delay_seconds(self):
        """End-to-end delay (GPS fix -> server), or None if the device sent no fix_time."""
        if self.fix_time is None:
            return None
        return round((self.received_at - self.fix_time).total_seconds(), 1)

    def __str__(self):
        return f"{self.bus} @ {self.received_at:%H:%M:%S}"