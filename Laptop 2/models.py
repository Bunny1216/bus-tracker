from django.db import models
from django.utils import timezone


class Route(models.Model):
    name = models.CharField(max_length=100)
    path = models.JSONField(default=list)  # [[lat, lng], [lat, lng], ...]

    def __str__(self):
        return self.name


class Stop(models.Model):
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="stops")
    name = models.CharField(max_length=100)
    lat = models.FloatField()
    lng = models.FloatField()
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.order}. {self.name}"


class Bus(models.Model):
    code = models.CharField(max_length=20, unique=True)
    route = models.ForeignKey(Route, null=True, blank=True, on_delete=models.SET_NULL)
    api_key = models.CharField(max_length=64)

    def __str__(self):
        return self.code


class Position(models.Model):
    bus = models.ForeignKey(Bus, on_delete=models.CASCADE, related_name="positions")
    lat = models.FloatField()
    lng = models.FloatField()
    speed = models.FloatField(default=0)      # km/h, as sent by the unit
    heading = models.FloatField(default=0)
    # When the GPS fix was taken (UTC, from the unit). Optional.
    fix_time = models.DateTimeField(null=True, blank=True)
    # When the server stored it. default= (not auto_now_add) so ingest can set it
    # explicitly and compute latency from the very same instant.
    received_at = models.DateTimeField(default=timezone.now)
    # received_at - fix_time, in seconds. Null when the unit sent no fix_time.
    latency_seconds = models.FloatField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["bus", "-received_at"])]
