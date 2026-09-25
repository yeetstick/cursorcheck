"""A direct regression in the upstream project's existing pytest style.

Intentionally fails on the unmodified pinned connector. This checks emitted
records using mocked HTTP, rather than a subprocess and a materialized sink.
"""

from tap_rest_api_msdk.tap import TapRestApiMsdk


def test_empty_middle_page_with_next_token(requests_mock):
    url = "https://example.com/records"
    first = [{"id": "alpha", "version": "1"}, {"id": "beta", "version": "1"}]
    last = [{"id": "gamma", "version": "2"}, {"id": "delta", "version": "2"}]
    for request_url, items, token in (
        (url, first, "second"),
        (url + "?cursor=second", [], "third"),
        (url + "?cursor=third", last, None),
    ):
        requests_mock.get(request_url, complete_qs=True, json={"items": items, "next": token})
    config = {
        "api_url": "https://example.com",
        "next_page_token_path": "$.next", "pagination_next_page_param": "cursor",
        "pagination_request_style": "jsonpath_paginator", "pagination_response_style": "page",
        "streams": [{"name": "records", "path": "/records", "primary_keys": ["id"],
                     "records_path": "$.items[*]", "schema": {"type": "object", "properties": {
                         "id": {"type": "string"}, "version": {"type": "string"}}}}],
    }
    stream = TapRestApiMsdk(config=config, parse_env_config=False).discover_streams()[0]
    assert list(stream.get_records({})) == first + last
