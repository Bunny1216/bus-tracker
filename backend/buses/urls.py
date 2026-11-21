from django.urls import path

from . import views

urlpatterns = [
    path("ingest/", views.ingest, name="ingest"),
    path("buses/", views.buses, name="buses"),
    path("routes/<int:pk>/", views.route_detail, name="route-detail"),
]