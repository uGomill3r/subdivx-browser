from django.urls import path

from series import views

app_name = "series"

urlpatterns = [
    path("", views.index, name="index"),
    path("api/folders/", views.list_folders_view, name="list_folders"),
    path("api/files/", views.list_files_view, name="list_files"),
    path("api/rename/", views.rename_files_view, name="rename_files"),
    path("api/suggest-title/", views.suggest_title_view, name="suggest_title"),
    path("api/subtitle-search/", views.subtitle_search_view, name="subtitle_search"),
    path("api/subtitle-download/", views.subtitle_download_view, name="subtitle_download"),
]