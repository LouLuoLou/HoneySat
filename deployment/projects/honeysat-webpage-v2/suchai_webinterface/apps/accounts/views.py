from django.shortcuts import redirect

from suchai_webinterface.settings import PERSONALITY


def base_view(request):
    context = PERSONALITY
    return redirect("login", context=context)
