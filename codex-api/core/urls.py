from advert.api import router as advert_router
from bill.api import router as bill_router
from django.urls import path
from django.urls import include
from django.shortcuts import redirect
from django.urls import reverse
from law.api import router as law_router
from ninja import NinjaAPI

api = NinjaAPI(title="Lagasafn-XML API", version="0.1.0")
api.add_router("/bill", bill_router)
api.add_router("/law", law_router)
api.add_router("/advert", advert_router)

# FIXME: We want to implement this but we need to make sure that messages can
# be displayed to the client, before deciding to display them all. Possibly
# this should only be used with a particular exception that is explicitly
# intended for the end user (like `EndUserException` or similar).
# @api.exception_handler(BillException)
# def service_unavailable(request, exc):
#     """
#     Handle exceptions gracefully. Specify custom HTTP error code and return with message intended.
#     """
#
#     return api.create_response(
#         request,
#         { "message": exc.__str__() },
#         status=400,
#     )

urlpatterns = [
    path("", lambda request: redirect(reverse("law_list")), name="home"),
    path("advert/", include("advert.urls")),
    path("law/", include("law.urls")),
    path("api/", api.urls),
]
