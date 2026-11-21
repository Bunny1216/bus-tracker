import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from buses.models import Bus, Route, Stop, generate_api_key


def _load_json(path: Path):
    if not path.is_file():
        raise CommandError(f"File not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CommandError(f"{path.name} is not valid JSON: {exc}")


class Command(BaseCommand):
    help = "Load data/route.json and data/stops.json and create BUS-01 (safe to re-run)."

    def add_arguments(self, parser):
        parser.add_argument("--data-dir", default=str(settings.REPO_ROOT / "data"))
        parser.add_argument("--route-name", default="Gazipur Chowrasta - Abdullahpur")
        parser.add_argument("--bus-code", default="BUS-01")
        parser.add_argument("--reset-key", action="store_true", help="Generate a new API key for the bus.")
        parser.add_argument("--show-key", action="store_true", help="Print the key even if the bus already existed.")

    @transaction.atomic
    def handle(self, *args, **opts):
        data_dir = Path(opts["data_dir"])
        path = _load_json(data_dir / "route.json")
        stops = _load_json(data_dir / "stops.json")

        if not (isinstance(path, list) and len(path) >= 2
                and all(isinstance(p, list) and len(p) == 2 and all(isinstance(v, (int, float)) for v in p) for p in path)):
            raise CommandError("route.json must be a list of [lat, lng] pairs (at least 2).")
        needed = {"name", "lat", "lng", "order"}
        if not (isinstance(stops, list) and all(isinstance(s, dict) and needed <= s.keys() for s in stops)):
            raise CommandError("stops.json must be a list of objects with name, lat, lng, order.")

        route, route_created = Route.objects.update_or_create(name=opts["route_name"], defaults={"path": path})

        for s in stops:
            Stop.objects.update_or_create(
                route=route, order=s["order"],
                defaults={"code": s.get("id", ""), "name": s["name"], "lat": s["lat"], "lng": s["lng"]},
            )
        route.stops.exclude(order__in=[s["order"] for s in stops]).delete()

        bus, bus_created = Bus.objects.get_or_create(code=opts["bus_code"], defaults={"route": route})
        changed = False
        if bus.route_id != route.pk:
            bus.route, changed = route, True
        if opts["reset_key"]:
            bus.api_key, changed = generate_api_key(), True
        if changed:
            bus.save()

        self.stdout.write(self.style.SUCCESS(
            f"Route '{route.name}' (id={route.pk}, {'created' if route_created else 'updated'}): "
            f"{len(path)} points, {len(stops)} stops."
        ))
        self.stdout.write(self.style.SUCCESS(f"Bus {bus.code} {'created' if bus_created else 'ready'}."))
        if bus_created or opts["reset_key"] or opts["show_key"]:
            self.stdout.write(f"API key for {bus.code}: {bus.api_key}")