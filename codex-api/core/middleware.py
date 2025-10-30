"""
Middleware to fix OpenAPI schema generation issues.
"""

import json
from django.http import JsonResponse
from lagasafn.models.law import Law
from pydantic.fields import FieldInfo


class OpenAPIFixMiddleware:
    """
    Middleware that intercepts OpenAPI schema requests and fixes schema issues.

    Specifically fixes the issue where Pydantic fields with default values
    are marked as optional in the OpenAPI schema even when they should be required.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only process OpenAPI JSON requests.
        if (
            request.path == "/api/openapi.json"
            and hasattr(response, "content")
            and response.status_code == 200
        ):

            try:
                # Parse the OpenAPI schema.
                schema = json.loads(response.content.decode("utf-8"))

                # Fix the schema.
                self.fix_schema(schema)

                # Return the fixed schema.
                return JsonResponse(schema, json_dumps_params={"indent": 2})

            except (json.JSONDecodeError, AttributeError):
                # If something goes wrong, return the original response.
                pass

        return response

    def fix_schema(self, schema):
        """
        Fix schema issues by marking specific fields as required.
        """
        if "components" not in schema or "schemas" not in schema["components"]:
            return

        schemas = schema["components"]["schemas"]

        # Define model classes and their corresponding schema names
        model_fixes = {
            "Law": Law,
            # Add more models here as needed:
            # 'Chapter': Chapter,
        }

        # Apply fixes for each model
        for schema_name, model_class in model_fixes.items():
            if schema_name in schemas:
                self.fix_model_schema(schemas[schema_name], model_class)

    def get_required_fields_from_model(self, model_class):
        """
        Extract field names that are marked with Field(required=True) in the Pydantic model.
        """
        required_fields = []

        # Get the model's field definitions
        for field_name, field_info in model_class.model_fields.items():
            # Check if this field has Field(required=True)
            if isinstance(field_info, FieldInfo):
                # Check if the field has json_schema_extra={'required': True}
                if (
                    hasattr(field_info, "json_schema_extra")
                    and isinstance(field_info.json_schema_extra, dict)
                    and field_info.json_schema_extra.get("required") is True
                ):
                    required_fields.append(field_name)

        return required_fields

    def fix_model_schema(self, model_schema, model_class):
        """
        Fix a model schema by ensuring fields marked with Field(required=True) are required.
        """
        if "required" not in model_schema:
            model_schema["required"] = []

        # Dynamically get fields marked with Field(required=True)
        required_fields = self.get_required_fields_from_model(model_class)

        for field in required_fields:
            if field not in model_schema["required"]:
                model_schema["required"].append(field)
