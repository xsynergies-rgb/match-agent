from django.http import JsonResponse


def not_found(request, exception=None):
    return JsonResponse({"message": "Not found.", "code": "not_found", "errors": {}}, status=404)


def server_error(request):
    return JsonResponse(
        {"message": "Something went wrong on our side.", "code": "server_error", "errors": {}}, status=500
    )
