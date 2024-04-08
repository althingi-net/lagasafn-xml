from django.urls import path
from django.urls import include
from django.shortcuts import redirect
from django.shortcuts import reverse

from law.api import api as law_api

urlpatterns = [
    path("", lambda request: redirect(reverse("law_list")), name="home"),
    path("law/", include("law.urls")),
    path("api/law/", law_api.urls),
]
