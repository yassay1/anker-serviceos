class ServiceError(Exception):
    def __init__(self, status: int, detail: str, *, code: str | None = None, current_version: int | None = None):
        self.status = status
        self.detail = detail
        self.code = code
        self.current_version = current_version
        super().__init__(detail)
