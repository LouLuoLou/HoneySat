import json
import os
from datetime import datetime
from random import randint

from utils.db_client import MongoDBActor


def request_serializer(request):
    return {
        'scheme': request.scheme,
        'body': str(request.body),
        'path': request.path,
        'path_info': request.path_info,
        'method': request.method,
        'content_type': request.content_type,
        'content_params': request.content_params,
        'headers': request.headers,
        # 'META': request.META,
        'COOKIES': request.COOKIES,
        # 'GET': request.GET,
        # 'POST': request.POST,
        # 'FILES': {},
        'user': {
            'is_authenticated': request.user.is_authenticated,
            'username': request.user.username,
            'email': request.user.email if hasattr(request.user, 'email') else None,
            'is_staff': request.user.is_staff,
            'is_superuser': request.user.is_superuser,
        },
        'session': {
            'session_key': request.session.session_key,
        },
    }


def response_serializer(response):
    return {
        'status_code': response.status_code,
        'content': response.content,
        'headers': response.headers,
    }


class MongoLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.

        response = self.get_response(request)

        # Code to be executed for each request/response after
        # the view is called.

        if request.path == '/telnet-output/' and os.getenv('DJANGO_DEBUG', 'None') == 'True':
            return response

        # Check if the MONGO_IP environment variable is set
        try:
            if os.environ['MONGO_IP']:
                serialized_request = request_serializer(request)
                serialized_response = response_serializer(response)

                data_to_store = {
                    "_id": str(
                        f"{datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")}_{serialized_request['method']}_" +
                        f"{serialized_request['path']}_{randint(0, 100)}"),
                    'time': datetime.now(),
                    'path': serialized_request['path'],
                    'request': serialized_request,
                    'response': serialized_response
                }

                if serialized_request['path'] == '/accounts/login/' and serialized_request['method'] == 'POST':
                    split_body = serialized_request['body'][2:-1].split('&')
                    username = None
                    password = None

                    for part in split_body:
                        key, value = part.split('=')
                        if key == 'username':
                            username = value
                        elif key == 'password':
                            password = value

                    data_to_store['login_attempt'] = {
                        'username': username,
                        'password': password,
                    }

                # print("MongoDB is enabled")
                MongoDBActor("webapp_middleware_requests").insert_data(data_to_store)
                print("Logged request and response to MongoDB")
        except KeyError:
            print("MONGO_IP environment variable is not set. Skipping MongoDB logging.")
        except Exception as e:
            print(f"An error occurred while trying to log to MongoDB: {e}")

        return response
