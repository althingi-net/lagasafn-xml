from django.urls import path

from law import views

urlpatterns = [
    path("list/", views.law_list, name="law_list"),
    path("content-search/", views.content_search, name="content_search"),
    path("search/", views.law_search, name="law_search"),
    path(
        "show/<path:identifier>/patched/",
        views.law_show_patched,
        name="law_show_patched",
    ),
    path(
        "show/<path:identifier>/comparison/",
        views.law_show,
        {"view_type": "comparison"},
        name="law_show_comparison",
    ),
    path(
        "show/compare/",
        views.law_compare,
        name="law_show_compare",
    ),
    path("show/<path:identifier>/", views.law_show, name="law_show"),
]
