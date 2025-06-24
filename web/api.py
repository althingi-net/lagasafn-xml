from ninja import NinjaAPI
from django.http import HttpRequest

api = NinjaAPI()

@api.get("/")
def hello(request: HttpRequest) -> str:
    return "Hello World"