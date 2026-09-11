"""Every HTTP operation advertises its actual success wire format."""
from __future__ import annotations

from logosforge.api import create_api
from logosforge.db import Database


def test_every_operation_has_a_typed_success_response() -> None:
    paths = create_api(db=Database()).openapi()["paths"]
    methods = {"get", "post", "put", "patch", "delete"}
    for path, path_item in paths.items():
        for method, operation in path_item.items():
            if method not in methods:
                continue
            successes = [
                response
                for code, response in operation.get("responses", {}).items()
                if str(code).startswith("2")
            ]
            assert successes, f"missing success response: {method.upper()} {path}"
            content_types = {
                content_type
                for response in successes
                for content_type in (response.get("content") or {})
            }
            if path == "/api/projects/{project_id}/events":
                assert "text/event-stream" in content_types
                continue
            json_schemas = [
                (response.get("content") or {}).get("application/json", {}).get("schema")
                for response in successes
            ]
            assert any(json_schemas), f"missing JSON schema: {method.upper()} {path}"
