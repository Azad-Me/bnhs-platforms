from __future__ import annotations

import json
import unittest

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from services.common.responses import (
    ApiExceptionRule,
    ApiResponse,
    handle_api_exceptions,
    register_api_exception_handlers,
)


class DomainError(Exception):
    pass


class ApiResponseTests(unittest.TestCase):
    def test_success_response_uses_common_envelope(self):
        response = ApiResponse[list[int]].success([1, 2])

        self.assertEqual(
            response.model_dump(),
            {"code": 1, "message": "Success", "data": [1, 2]},
        )

class ApiExceptionDecoratorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.decorate = handle_api_exceptions(
            {
                DomainError: ApiExceptionRule(
                    status_code=409,
                    detail=lambda error: str(error),
                )
            }
        )

    async def test_mapped_exception_becomes_http_exception(self):
        @self.decorate
        async def endpoint():
            raise DomainError("Conflicting value.")

        with self.assertRaises(HTTPException) as caught:
            await endpoint()

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.detail, "Conflicting value.")

    async def test_unmapped_exceptions_are_not_swallowed(self):
        @self.decorate
        async def endpoint():
            raise ValueError("unexpected failure")

        with self.assertRaisesRegex(ValueError, "unexpected failure"):
            await endpoint()

    async def test_existing_http_exceptions_are_preserved(self):
        @self.decorate
        async def endpoint():
            raise HTTPException(status_code=401, detail="Unauthorized")

        with self.assertRaises(HTTPException) as caught:
            await endpoint()

        self.assertEqual(caught.exception.status_code, 401)

    async def test_successful_endpoint_result_is_unchanged(self):
        @self.decorate
        async def endpoint(value: int) -> int:
            return value

        self.assertEqual(await endpoint(3), 3)


class ApiExceptionHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        app = FastAPI()
        register_api_exception_handlers(app)
        self.handlers = app.exception_handlers
        self.request = Request(
            {"type": "http", "method": "GET", "path": "/test"}
        )

    async def test_validation_errors_use_common_envelope_with_details(self):
        error = RequestValidationError(
            [
                {
                    "loc": ("query", "limit"),
                    "msg": "Input should be greater than 0",
                    "type": "greater_than",
                    "input": 0,
                }
            ]
        )
        handler = self.handlers[RequestValidationError]

        response = await handler(self.request, error)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            json.loads(response.body),
            {
                "code": -1,
                "message": "Failed",
                "data": None,
                "errors": [
                    {
                        "loc": ["query", "limit"],
                        "message": "Input should be greater than 0",
                        "type": "greater_than",
                    }
                ],
            },
        )

    async def test_http_errors_keep_status_and_authentication_headers(self):
        error = StarletteHTTPException(
            status_code=401,
            detail="Authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        handler = self.handlers[StarletteHTTPException]

        response = await handler(self.request, error)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")
        self.assertEqual(
            json.loads(response.body),
            {
                "code": -1,
                "message": "Failed",
                "data": None,
                "errors": [
                    {
                        "message": "Authentication is required.",
                        "type": "http_error",
                    }
                ],
            },
        )


if __name__ == "__main__":
    unittest.main()
