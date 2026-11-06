from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from functools import wraps
import logging
from typing import Generic, ParamSpec, TypeVar

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException


logger = logging.getLogger(__name__)
ResponseData = TypeVar("ResponseData")
P = ParamSpec("P")
R = TypeVar("R")
ExceptionDetail = str | Callable[[Exception], str]


@dataclass(frozen=True)
class ApiExceptionRule:
    status_code: int
    detail: ExceptionDetail
    log_message: str | None = None


def handle_api_exceptions(
    rules: Mapping[type[Exception], ApiExceptionRule],
) -> Callable[
    [Callable[P, Awaitable[R]]],
    Callable[P, Awaitable[R]],
]:
    """Translate configured domain exceptions into HTTP errors for an endpoint."""
    def decorate(
        endpoint: Callable[P, Awaitable[R]],
    ) -> Callable[P, Awaitable[R]]:
        @wraps(endpoint)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return await endpoint(*args, **kwargs)
            except HTTPException:
                raise
            except Exception as error:
                for exception_type, rule in rules.items():
                    if isinstance(error, exception_type):
                        if rule.log_message is not None:
                            logger.warning(
                                "%s (exception=%s)",
                                rule.log_message,
                                exception_type.__name__,
                            )
                        detail = (
                            rule.detail(error)
                            if callable(rule.detail)
                            else rule.detail
                        )
                        raise HTTPException(
                            status_code=rule.status_code,
                            detail=detail,
                        ) from error
                raise

        return wrapped

    return decorate


class ApiErrorDetail(BaseModel):
    loc: list[str | int] | None = None
    message: str
    type: str | None = None


class ApiResponse(BaseModel, Generic[ResponseData]):
    code: int
    message: str
    data: ResponseData

    @classmethod
    def success(cls, data: ResponseData) -> ApiResponse[ResponseData]:
        return cls(code=1, message="Success", data=data)


class ApiErrorResponse(ApiResponse[None]):
    errors: list[ApiErrorDetail] | None = None


API_ERROR_RESPONSES = {
    status_code: {
        "model": ApiErrorResponse,
        "description": "Standard API error response.",
    }
    for status_code in (400, 401, 403, 404, 409, 422, 500, 502)
}


def register_api_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        errors = [
            ApiErrorDetail(
                loc=list(item["loc"]),
                message=item["msg"],
                type=item["type"],
            )
            for item in error.errors()
        ]
        return _error_response(422, errors=errors)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request,
        error: StarletteHTTPException,
    ) -> JSONResponse:
        errors = None
        if isinstance(error.detail, str):
            errors = [
                ApiErrorDetail(message=error.detail, type="http_error")
            ]
        return _error_response(
            error.status_code,
            errors=errors,
            headers=error.headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(
        request: Request,
        error: Exception,
    ) -> JSONResponse:
        logger.exception(
            "Unhandled API error for %s %s",
            request.method,
            request.url.path,
        )
        return _error_response(500)


def _error_response(
    status_code: int,
    *,
    errors: list[ApiErrorDetail] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    response = ApiErrorResponse(
        code=-1,
        message="Failed",
        data=None,
        errors=errors,
    )
    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json", exclude_none=True)
        | {"data": None},
        headers=headers,
    )
