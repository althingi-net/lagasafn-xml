from ninja.security import HttpBearer
from mechlaw.settings import API_ACCESS_TOKEN

class APIAuthentication(HttpBearer):
    """
    Validates incoming API requests using access token.
    """
    def authenticate(self, request, token):
        if token == API_ACCESS_TOKEN:
            return token
