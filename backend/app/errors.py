class ApiError(Exception):
    """统一的业务错误，序列化为 JSON：{error: {...}}。"""

    def __init__(self, status: int, message: str, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code or {
            400: "bad_request",
            404: "not_found",
            409: "conflict",
            422: "unprocessable",
        }.get(status, "error")

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message}}
