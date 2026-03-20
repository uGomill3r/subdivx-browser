from django.urls import path
from browser import views

app_name = "browser"

urlpatterns = [
    path("", views.index, name="index"),
    path("folders/", views.folder_list, name="folder_list"),
    path("folder/<str:folder_name>/", views.folder_detail, name="folder_detail"),
    path("folder/<str:folder_name>/search/", views.search_subtitles_view, name="search_subtitles"),
    path("folder/<str:folder_name>/download/", views.download_and_save, name="download_and_save"),
]