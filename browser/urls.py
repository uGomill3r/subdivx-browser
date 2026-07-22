from django.urls import path
from browser import views

app_name = "browser"

urlpatterns = [
    path("", views.index, name="index"),
    path("folders/", views.folder_list, name="folder_list"),
    path("folder/<str:folder_name>/move/", views.move_folder_view, name="move_folder"),
    path("folder/<str:folder_name>/", views.folder_detail, name="folder_detail"),
    path("folder/<str:folder_name>/search/", views.search_subtitles_view, name="search_subtitles"),
    path("folder/<str:folder_name>/download/", views.download_and_save, name="download_and_save"),
    path("folder/<str:folder_name>/select/", views.select_and_save, name="select_and_save"),
    path("settings/", views.settings_view, name="settings"),
    path("settings/test-api/", views.test_api_connection_view, name="test_api_connection"),
    path("settings/cf-cookie/start/", views.cf_cookie_capture_start, name="cf_cookie_start"),
    path("settings/cf-cookie/status/", views.cf_cookie_capture_status, name="cf_cookie_status"),
    path("settings/cf-cookie/click/", views.cf_cookie_capture_click, name="cf_cookie_click"),
    path("settings/cf-cookie/cancel/", views.cf_cookie_capture_cancel, name="cf_cookie_cancel"),
    path("logs/", views.logs_view, name="logs"),
]