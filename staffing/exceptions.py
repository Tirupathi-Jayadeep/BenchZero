from django.db.models import ProtectedError
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None and isinstance(exc, ProtectedError):
        protected_objects = list(exc.protected_objects)
        model_name = protected_objects[0]._meta.verbose_name.title() if protected_objects else "related record"
        return Response(
            {
                'error': f"Cannot delete object because active or historical {model_name} records refer to it. "
                         f"Cancel or clear related allocations first."
            },
            status=status.HTTP_409_CONFLICT
        )
    return response
