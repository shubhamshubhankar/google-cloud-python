# Copyright 2015 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import unittest

import mock
import requests
from six.moves import http_client


def _make_credentials():
    import google.auth.credentials

    return mock.Mock(spec=google.auth.credentials.Credentials)


def _make_response(status=http_client.OK, content=b'', headers={}):
    response = requests.Response()
    response.status_code = status
    response._content = content
    response.headers = headers
    response.request = requests.Request()
    return response


def _make_json_response(data, status=http_client.OK, headers=None):
    headers = headers or {}
    headers['Content-Type'] = 'application/json'
    return _make_response(
        status=status,
        content=json.dumps(data).encode('utf-8'),
        headers=headers)


def _make_requests_session(responses):
    session = mock.create_autospec(requests.Session, instance=True)
    session.request.side_effect = responses
    return session


class TestClient(unittest.TestCase):

    @staticmethod
    def _get_target_class():
        from google.cloud.storage.client import Client

        return Client

    def _make_one(self, *args, **kw):
        return self._get_target_class()(*args, **kw)

    def test_ctor_connection_type(self):
        from google.cloud.storage._http import Connection

        PROJECT = 'PROJECT'
        CREDENTIALS = _make_credentials()

        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)

        self.assertEqual(client.project, PROJECT)
        self.assertIsInstance(client._connection, Connection)
        self.assertIs(client._connection.credentials, CREDENTIALS)
        self.assertIsNone(client.current_batch)
        self.assertEqual(list(client._batch_stack), [])

    def test_ctor_wo_project(self):
        from google.cloud.storage._http import Connection

        PROJECT = 'PROJECT'
        CREDENTIALS = _make_credentials()

        ddp_patch = mock.patch(
            'google.cloud.client._determine_default_project',
            return_value=PROJECT)

        with ddp_patch:
            client = self._make_one(credentials=CREDENTIALS)

        self.assertEqual(client.project, PROJECT)
        self.assertIsInstance(client._connection, Connection)
        self.assertIs(client._connection.credentials, CREDENTIALS)
        self.assertIsNone(client.current_batch)
        self.assertEqual(list(client._batch_stack), [])

    def test_ctor_w_project_explicit_none(self):
        from google.cloud.storage._http import Connection

        CREDENTIALS = _make_credentials()

        client = self._make_one(project=None, credentials=CREDENTIALS)

        self.assertIsNone(client.project)
        self.assertIsInstance(client._connection, Connection)
        self.assertIs(client._connection.credentials, CREDENTIALS)
        self.assertIsNone(client.current_batch)
        self.assertEqual(list(client._batch_stack), [])

    def test_create_anonymous_client(self):
        from google.auth.credentials import AnonymousCredentials
        from google.cloud.storage._http import Connection

        klass = self._get_target_class()
        client = klass.create_anonymous_client()

        self.assertIsNone(client.project)
        self.assertIsInstance(client._connection, Connection)
        self.assertIsInstance(
            client._connection.credentials, AnonymousCredentials)

    def test__push_batch_and__pop_batch(self):
        from google.cloud.storage.batch import Batch

        PROJECT = 'PROJECT'
        CREDENTIALS = _make_credentials()

        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)
        batch1 = Batch(client)
        batch2 = Batch(client)
        client._push_batch(batch1)
        self.assertEqual(list(client._batch_stack), [batch1])
        self.assertIs(client.current_batch, batch1)
        client._push_batch(batch2)
        self.assertIs(client.current_batch, batch2)
        # list(_LocalStack) returns in reverse order.
        self.assertEqual(list(client._batch_stack), [batch2, batch1])
        self.assertIs(client._pop_batch(), batch2)
        self.assertEqual(list(client._batch_stack), [batch1])
        self.assertIs(client._pop_batch(), batch1)
        self.assertEqual(list(client._batch_stack), [])

    def test__connection_setter(self):
        PROJECT = 'PROJECT'
        CREDENTIALS = _make_credentials()
        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)
        client._base_connection = None  # Unset the value from the constructor
        client._connection = connection = object()
        self.assertIs(client._base_connection, connection)

    def test__connection_setter_when_set(self):
        PROJECT = 'PROJECT'
        CREDENTIALS = _make_credentials()
        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)
        self.assertRaises(ValueError, setattr, client, '_connection', None)

    def test__connection_getter_no_batch(self):
        PROJECT = 'PROJECT'
        CREDENTIALS = _make_credentials()
        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)
        self.assertIs(client._connection, client._base_connection)
        self.assertIsNone(client.current_batch)

    def test__connection_getter_with_batch(self):
        from google.cloud.storage.batch import Batch

        PROJECT = 'PROJECT'
        CREDENTIALS = _make_credentials()
        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)
        batch = Batch(client)
        client._push_batch(batch)
        self.assertIsNot(client._connection, client._base_connection)
        self.assertIs(client._connection, batch)
        self.assertIs(client.current_batch, batch)

    def test_get_service_account_email_wo_project(self):
        PROJECT = 'PROJECT'
        CREDENTIALS = _make_credentials()
        EMAIL = 'storage-user-123@example.com'
        RESOURCE = {
            'kind': 'storage#serviceAccount',
            'email_address': EMAIL,
        }

        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)
        http = _make_requests_session([
            _make_json_response(RESOURCE)])
        client._http_internal = http

        service_account_email = client.get_service_account_email()

        self.assertEqual(service_account_email, EMAIL)
        URI = '/'.join([
            client._connection.API_BASE_URL,
            'storage',
            client._connection.API_VERSION,
            'projects/%s/serviceAccount' % (PROJECT,)
        ])
        http.request.assert_called_once_with(
            method='GET', url=URI, data=None, headers=mock.ANY)

    def test_get_service_account_email_w_project(self):
        PROJECT = 'PROJECT'
        OTHER_PROJECT = 'OTHER_PROJECT'
        CREDENTIALS = _make_credentials()
        EMAIL = 'storage-user-123@example.com'
        RESOURCE = {
            'kind': 'storage#serviceAccount',
            'email_address': EMAIL,
        }

        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)
        http = _make_requests_session([
            _make_json_response(RESOURCE)])
        client._http_internal = http

        service_account_email = client.get_service_account_email(
            project=OTHER_PROJECT)

        self.assertEqual(service_account_email, EMAIL)
        URI = '/'.join([
            client._connection.API_BASE_URL,
            'storage',
            client._connection.API_VERSION,
            'projects/%s/serviceAccount' % (OTHER_PROJECT,)
        ])
        http.request.assert_called_once_with(
            method='GET', url=URI, data=None, headers=mock.ANY)

    def test_bucket(self):
        from google.cloud.storage.bucket import Bucket

        PROJECT = 'PROJECT'
        CREDENTIALS = _make_credentials()
        BUCKET_NAME = 'BUCKET_NAME'

        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)
        bucket = client.bucket(BUCKET_NAME)
        self.assertIsInstance(bucket, Bucket)
        self.assertIs(bucket.client, client)
        self.assertEqual(bucket.name, BUCKET_NAME)
        self.assertIsNone(bucket.user_project)

    def test_bucket_w_user_project(self):
        from google.cloud.storage.bucket import Bucket

        PROJECT = 'PROJECT'
        USER_PROJECT = 'USER_PROJECT'
        CREDENTIALS = _make_credentials()
        BUCKET_NAME = 'BUCKET_NAME'

        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)
        bucket = client.bucket(BUCKET_NAME, user_project=USER_PROJECT)
        self.assertIsInstance(bucket, Bucket)
        self.assertIs(bucket.client, client)
        self.assertEqual(bucket.name, BUCKET_NAME)
        self.assertEqual(bucket.user_project, USER_PROJECT)

    def test_batch(self):
        from google.cloud.storage.batch import Batch

        PROJECT = 'PROJECT'
        CREDENTIALS = _make_credentials()

        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)
        batch = client.batch()
        self.assertIsInstance(batch, Batch)
        self.assertIs(batch._client, client)

    def test_get_bucket_miss(self):
        from google.cloud.exceptions import NotFound

        PROJECT = 'PROJECT'
        CREDENTIALS = _make_credentials()
        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)

        NONESUCH = 'nonesuch'
        URI = '/'.join([
            client._connection.API_BASE_URL,
            'storage',
            client._connection.API_VERSION,
            'b',
            'nonesuch?projection=noAcl',
        ])
        http = _make_requests_session([
            _make_json_response({}, status=http_client.NOT_FOUND)])
        client._http_internal = http

        with self.assertRaises(NotFound):
            client.get_bucket(NONESUCH)

        http.request.assert_called_once_with(
            method='GET', url=URI, data=mock.ANY, headers=mock.ANY)

    def test_get_bucket_hit(self):
        from google.cloud.storage.bucket import Bucket

        PROJECT = 'PROJECT'
        CREDENTIALS = _make_credentials()
        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)

        BUCKET_NAME = 'bucket-name'
        URI = '/'.join([
            client._connection.API_BASE_URL,
            'storage',
            client._connection.API_VERSION,
            'b',
            '%s?projection=noAcl' % (BUCKET_NAME,),
        ])

        data = {'name': BUCKET_NAME}
        http = _make_requests_session([_make_json_response(data)])
        client._http_internal = http

        bucket = client.get_bucket(BUCKET_NAME)

        self.assertIsInstance(bucket, Bucket)
        self.assertEqual(bucket.name, BUCKET_NAME)
        http.request.assert_called_once_with(
            method='GET', url=URI, data=mock.ANY, headers=mock.ANY)

    def test_lookup_bucket_miss(self):
        PROJECT = 'PROJECT'
        CREDENTIALS = _make_credentials()
        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)

        NONESUCH = 'nonesuch'
        URI = '/'.join([
            client._connection.API_BASE_URL,
            'storage',
            client._connection.API_VERSION,
            'b',
            'nonesuch?projection=noAcl',
        ])
        http = _make_requests_session([
            _make_json_response({}, status=http_client.NOT_FOUND)])
        client._http_internal = http

        bucket = client.lookup_bucket(NONESUCH)

        self.assertIsNone(bucket)
        http.request.assert_called_once_with(
            method='GET', url=URI, data=mock.ANY, headers=mock.ANY)

    def test_lookup_bucket_hit(self):
        from google.cloud.storage.bucket import Bucket

        PROJECT = 'PROJECT'
        CREDENTIALS = _make_credentials()
        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)

        BUCKET_NAME = 'bucket-name'
        URI = '/'.join([
            client._connection.API_BASE_URL,
            'storage',
            client._connection.API_VERSION,
            'b',
            '%s?projection=noAcl' % (BUCKET_NAME,),
        ])
        data = {'name': BUCKET_NAME}
        http = _make_requests_session([_make_json_response(data)])
        client._http_internal = http

        bucket = client.lookup_bucket(BUCKET_NAME)

        self.assertIsInstance(bucket, Bucket)
        self.assertEqual(bucket.name, BUCKET_NAME)
        http.request.assert_called_once_with(
            method='GET', url=URI, data=mock.ANY, headers=mock.ANY)

    def test_create_bucket_conflict(self):
        from google.cloud.exceptions import Conflict

        PROJECT = 'PROJECT'
        OTHER_PROJECT = 'OTHER_PROJECT'
        CREDENTIALS = _make_credentials()
        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)

        BUCKET_NAME = 'bucket-name'
        URI = '/'.join([
            client._connection.API_BASE_URL,
            'storage',
            client._connection.API_VERSION,
            'b?project=%s' % (OTHER_PROJECT,),
        ])
        data = {'error': {'message': 'Conflict'}}
        sent = {'name': BUCKET_NAME}
        http = _make_requests_session([
            _make_json_response(data, status=http_client.CONFLICT)])
        client._http_internal = http

        with self.assertRaises(Conflict):
            client.create_bucket(BUCKET_NAME, project=OTHER_PROJECT)

        http.request.assert_called_once_with(
            method='POST', url=URI, data=mock.ANY, headers=mock.ANY)
        json_sent = http.request.call_args_list[0][1]['data']
        self.assertEqual(sent, json.loads(json_sent))

    def test_create_bucket_success(self):
        from google.cloud.storage.bucket import Bucket

        PROJECT = 'PROJECT'
        CREDENTIALS = _make_credentials()
        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)

        BUCKET_NAME = 'bucket-name'
        URI = '/'.join([
            client._connection.API_BASE_URL,
            'storage',
            client._connection.API_VERSION,
            'b?project=%s' % (PROJECT,),
        ])
        sent = {'name': BUCKET_NAME, 'billing': {'requesterPays': True}}
        data = sent
        http = _make_requests_session([_make_json_response(data)])
        client._http_internal = http

        bucket = client.create_bucket(BUCKET_NAME, requester_pays=True)

        self.assertIsInstance(bucket, Bucket)
        self.assertEqual(bucket.name, BUCKET_NAME)
        self.assertTrue(bucket.requester_pays)
        http.request.assert_called_once_with(
            method='POST', url=URI, data=mock.ANY, headers=mock.ANY)
        json_sent = http.request.call_args_list[0][1]['data']
        self.assertEqual(sent, json.loads(json_sent))

    def test_list_buckets_wo_project(self):
        CREDENTIALS = _make_credentials()
        client = self._make_one(project=None, credentials=CREDENTIALS)

        with self.assertRaises(ValueError):
            client.list_buckets()

    def test_list_buckets_empty(self):
        from six.moves.urllib.parse import parse_qs
        from six.moves.urllib.parse import urlparse

        PROJECT = 'PROJECT'
        CREDENTIALS = _make_credentials()
        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)

        http = _make_requests_session([_make_json_response({})])
        client._http_internal = http

        buckets = list(client.list_buckets())

        self.assertEqual(len(buckets), 0)

        http.request.assert_called_once_with(
            method='GET', url=mock.ANY, data=mock.ANY, headers=mock.ANY)

        requested_url = http.request.mock_calls[0][2]['url']
        expected_base_url = '/'.join([
            client._connection.API_BASE_URL,
            'storage',
            client._connection.API_VERSION,
            'b',
        ])
        self.assertTrue(requested_url.startswith(expected_base_url))

        expected_query = {
            'project': [PROJECT],
            'projection': ['noAcl'],
        }
        uri_parts = urlparse(requested_url)
        self.assertEqual(parse_qs(uri_parts.query), expected_query)

    def test_list_buckets_explicit_project(self):
        from six.moves.urllib.parse import parse_qs
        from six.moves.urllib.parse import urlparse

        PROJECT = 'PROJECT'
        OTHER_PROJECT = 'OTHER_PROJECT'
        CREDENTIALS = _make_credentials()
        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)

        http = _make_requests_session([_make_json_response({})])
        client._http_internal = http

        buckets = list(client.list_buckets(project=OTHER_PROJECT))

        self.assertEqual(len(buckets), 0)

        http.request.assert_called_once_with(
            method='GET', url=mock.ANY, data=mock.ANY, headers=mock.ANY)

        requested_url = http.request.mock_calls[0][2]['url']
        expected_base_url = '/'.join([
            client._connection.API_BASE_URL,
            'storage',
            client._connection.API_VERSION,
            'b',
        ])
        self.assertTrue(requested_url.startswith(expected_base_url))

        expected_query = {
            'project': [OTHER_PROJECT],
            'projection': ['noAcl'],
        }
        uri_parts = urlparse(requested_url)
        self.assertEqual(parse_qs(uri_parts.query), expected_query)

    def test_list_buckets_non_empty(self):
        PROJECT = 'PROJECT'
        CREDENTIALS = _make_credentials()
        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)

        BUCKET_NAME = 'bucket-name'

        data = {'items': [{'name': BUCKET_NAME}]}
        http = _make_requests_session([_make_json_response(data)])
        client._http_internal = http

        buckets = list(client.list_buckets())

        self.assertEqual(len(buckets), 1)
        self.assertEqual(buckets[0].name, BUCKET_NAME)

        http.request.assert_called_once_with(
            method='GET', url=mock.ANY, data=mock.ANY, headers=mock.ANY)

    def test_list_buckets_all_arguments(self):
        from six.moves.urllib.parse import parse_qs
        from six.moves.urllib.parse import urlparse

        PROJECT = 'foo-bar'
        CREDENTIALS = _make_credentials()
        client = self._make_one(project=PROJECT, credentials=CREDENTIALS)

        MAX_RESULTS = 10
        PAGE_TOKEN = 'ABCD'
        PREFIX = 'subfolder'
        PROJECTION = 'full'
        FIELDS = 'items/id,nextPageToken'

        data = {'items': []}
        http = _make_requests_session([_make_json_response(data)])
        client._http_internal = http
        iterator = client.list_buckets(
            max_results=MAX_RESULTS,
            page_token=PAGE_TOKEN,
            prefix=PREFIX,
            projection=PROJECTION,
            fields=FIELDS,
        )
        buckets = list(iterator)
        self.assertEqual(buckets, [])
        http.request.assert_called_once_with(
            method='GET', url=mock.ANY, data=mock.ANY, headers=mock.ANY)

        requested_url = http.request.mock_calls[0][2]['url']
        expected_base_url = '/'.join([
            client._connection.API_BASE_URL,
            'storage',
            client._connection.API_VERSION,
            'b',
        ])
        self.assertTrue(requested_url.startswith(expected_base_url))

        expected_query = {
            'project': [PROJECT],
            'maxResults': [str(MAX_RESULTS)],
            'pageToken': [PAGE_TOKEN],
            'prefix': [PREFIX],
            'projection': [PROJECTION],
            'fields': [FIELDS],
        }
        uri_parts = urlparse(requested_url)
        self.assertEqual(parse_qs(uri_parts.query), expected_query)

    def test_page_empty_response(self):
        from google.api_core import page_iterator

        project = 'PROJECT'
        credentials = _make_credentials()
        client = self._make_one(project=project, credentials=credentials)
        iterator = client.list_buckets()
        page = page_iterator.Page(iterator, (), None)
        iterator._page = page
        self.assertEqual(list(page), [])

    def test_page_non_empty_response(self):
        import six
        from google.cloud.storage.bucket import Bucket

        project = 'PROJECT'
        credentials = _make_credentials()
        client = self._make_one(project=project, credentials=credentials)

        blob_name = 'bucket-name'
        response = {'items': [{'name': blob_name}]}

        def dummy_response():
            return response

        iterator = client.list_buckets()
        iterator._get_next_page_response = dummy_response

        page = six.next(iterator.pages)
        self.assertEqual(page.num_items, 1)
        bucket = six.next(page)
        self.assertEqual(page.remaining, 0)
        self.assertIsInstance(bucket, Bucket)
        self.assertEqual(bucket.name, blob_name)
