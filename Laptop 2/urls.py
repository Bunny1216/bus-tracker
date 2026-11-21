from django.urls import path

from . import dashboard_views, views

urlpatterns = [
    path("api/ingest/", views.ingest, name="ingest"),
    path("api/buses/", views.buses, name="buses"),
    path("api/routes/<int:pk>/", views.route_detail, name="route_detail"),
    path("api/stops/<int:pk>/etas/", views.stop_etas, name="stop_etas"),
    path("api/export/positions/", dashboard_views.export_positions, name="export_positions"),
    path("dashboard/", dashboard_views.dashboard, name="dashboard"),
]
