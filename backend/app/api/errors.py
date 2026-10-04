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
    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        return error_response(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Never echo input (password, URL/query, cookie) or arbitrary validator context.
        details = [
            {"field": ".".join(str(x) for x in e["loc"]), "type": e["type"]} for e in exc.errors()
        ]
        return error_response(422, "validation_error", "Request validation failed", details)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        return error_response(503, "database_unavailable", "Database temporarily unavailable")

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        return error_response(500, "internal_error", "Unexpected server error")
