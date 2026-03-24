import os

import requests
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse
import socket

from suchai_webinterface.settings import PERSONALITY


@login_required
def dashboard_base_view(request):
    context = PERSONALITY
    return render(request, 'dashboard/dashboard_base.html', context)


@login_required
def web_interface_view(request):
    context = PERSONALITY
    return render(request, 'dashboard/web_interface.html', context)


@login_required
def remote_desktop_view(request):


    vnc_port = os.environ.get('VNC_PORT', '8080')
    vnc_password = os.environ.get('VNC_PASSWORD', 'kEmju7vu')

    hostname_from_request = request.headers.get("Host")
    hostname_from_request_cleaned = hostname_from_request.split(':')[0] if hostname_from_request else None

    vnc_host = os.environ.get('VNC_HOST', hostname_from_request_cleaned)
    vnc_host_with_port = vnc_host + ":" + vnc_port
    vnc_url = f'http://{vnc_host_with_port}/vnc.html?autoconnect=true&password={vnc_password}&reconnect=true&resize=scale'

    # vnc_url = "http://200.9.100.153:8080/vnc.html?autoconnect=true&password=kEmju7vu&reconnect=true&resize=scale"
    context = {
        'vnc_url': vnc_url,
    }
    context.update(PERSONALITY)
    return render(request, 'dashboard/remote_desktop_vnc.html', context)


@login_required
def docs_plain_view(request):
    context = PERSONALITY
    return render(request, 'dashboard/docs_plain.html', context)


@login_required
def docs_hugo_view(request):
    context = PERSONALITY

    try:
        response = requests.get(PERSONALITY["FAKE_DOCS_V2_URL"])
        response.raise_for_status()  # Raise an exception for HTTP errors

        # Add the downloaded text to the context
        context["docs_description"] = response.text

        # print("Text successfully added to the context:")
        # print(context)

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while fetching the URL: {e}")
        context["docs_description"] = "Work in progress"

    return render(request, 'dashboard/docs_hugo.html', context)


@login_required
def get_telnet_output(request):
    socket_host = 'localhost'
    socket_port = 9999
    keywords_to_filter = ['honeysat', 'honeypot', '[tcp://honeysat-api:8002]', 'tcp://honeysat-api:8001']

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((socket_host, socket_port))
            data = sock.recv(40960).decode('utf-8')
    except ConnectionError as e:
        return JsonResponse({'error': str(e)}, status=500)

    # Split the data into lines
    lines = data.splitlines()

    # Filter out lines containing any of the keywords
    filtered_lines = [line for line in lines if not any(keyword in line for keyword in keywords_to_filter)]

    return JsonResponse({'output': filtered_lines})
