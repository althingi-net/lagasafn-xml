from advert import views
from django.urls import path

urlpatterns = [
    path("list/", views.advert_list, name="advert_list"),
]
