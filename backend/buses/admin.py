from django.contrib import admin

from .models import Bus, Position, Route, Stop


class StopInline(admin.TabularInline):
    model = Stop
    extra = 0
    ordering = ("order",)


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ("name", "point_count", "stop_count")
    inlines = [StopInline]

    @admin.display(description="Path points")
    def point_count(self, obj):
        return len(obj.path or [])

    @admin.display(description="Stops")
    def stop_count(self, obj):
        return obj.stops.count()


@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):
    list_display = ("code", "route", "last_seen")

    @admin.display(description="Last seen")
    def last_seen(self, obj):
        p = obj.positions.order_by("-received_at").first()
        return p.received_at if p else None


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("bus", "lat", "lng", "speed", "heading", "fix_time", "received_at", "delay")
    list_filter = ("bus",)
    list_select_related = ("bus",)
    date_hierarchy = "received_at"
    readonly_fields = ("received_at",)

    @admin.display(description="Delay (s)")
    def delay(self, obj):
        return obj.delay_seconds