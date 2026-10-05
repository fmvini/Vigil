from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details


def error_response(status, code, message, details=None):
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
            }
        },
    )


def install_handlers(app):
    def response(request, status, code, message, details=None):
        request.state.error_code = code
        result = error_response(status, code, message, details)
        # ServerErrorMiddleware lives outside user middleware; correlate its 500 too.
        if identifier := getattr(request.state, "request_id", None):
            result.headers["X-Request-ID"] = identifier
        return result

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        return response(request, exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Never echo input (password, URL/query, cookie) or arbitrary validator context.
        details = []
        for error in exc.errors():
            # An extra key is caller input, unlike a declared model field. Report
            # its parent while keeping known field paths usable by the frontend.
            location = error["loc"][:-1] if error["type"] == "extra_forbidden" else error["loc"]
            details.append({"field": ".".join(str(x) for x in location), "type": error["type"]})
        return response(request, 422, "validation_error", "Request validation failed", details)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return response(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        return response(request, 503, "database_unavailable", "Database temporarily unavailable")

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        return response(request, 500, "internal_error", "Unexpected server error")
