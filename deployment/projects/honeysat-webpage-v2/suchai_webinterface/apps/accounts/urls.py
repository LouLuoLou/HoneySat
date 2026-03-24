from lib2to3.fixes.fix_input import context

from django.urls import path

from django.contrib.auth import views as auth_views
from suchai_webinterface.settings import PERSONALITY


from .views import base_view

context_url = PERSONALITY

urlpatterns = [
    path('', base_view, name='base_view'),  # Home page loads the base view
    path("login/", auth_views.LoginView.as_view(template_name="accounts/login.html", extra_context=context_url), name="login"),
    path("logout/", auth_views.LogoutView.as_view(extra_context=context_url), name="logout"),
]
