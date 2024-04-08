from django.urls import path

from law import views

urlpatterns = [
    path("list/", views.law_list, name="law_list"),
    path("show/<path:identifier>/", views.law_show, name="law_show"),
]
