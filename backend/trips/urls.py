from django.urls import path

from trips import views

urlpatterns = [
    path("health", views.HealthView.as_view()),
    path("geocode", views.GeocodeView.as_view()),
    path("route-sets", views.RouteSetCreateView.as_view()),
    path("route-sets/<str:rs_id>/assessment", views.AssessmentView.as_view()),
    path("route-sets/<str:rs_id>/heatmap", views.HeatmapView.as_view()),
]
