from django.urls import path

from law import views

urlpatterns = [
    path("list/", views.law_list, name="law_list"),
    path(
        "show/<path:identifier>/cleaned/",
        views.law_show_cleaned,
        name="law_show_cleaned",
    ),
    path(
        "show/<path:identifier>/comparison/",
        views.law_show,
        {"view_type": "comparison"},
        name="law_show_comparison",
    ),
    path("show/<path:identifier>/", views.law_show, name="law_show"),
]
