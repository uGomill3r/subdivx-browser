from django.urls import path, include

urlpatterns = [
    path("", include("browser.urls", namespace="browser")),
    path("series/", include("series.urls", namespace="series")),
]