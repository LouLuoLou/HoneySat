from django.urls import path

from django.contrib.auth import views as auth_views

from .views import *

urlpatterns = [
    path('', web_interface_view, name='web_interface'),
    path('index/', web_interface_view, name='web_interface'),
    path('remote-desktop/', remote_desktop_view, name='remote_desktop'),
    path('docs/plain/', docs_plain_view, name='docs_plain'),
    path('docs/hugo/', docs_hugo_view, name='docs_hugo'),
    path('telnet-output/', get_telnet_output, name='telnet_output'),
]
