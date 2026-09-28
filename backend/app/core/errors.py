"""Application error types.

Each error carries a user-friendly message; technical detail goes to logs only.
"""


class AppError(Exception):
    status_code = 500
    user_message = "An unexpected error occurred. Please try again."

    def __init__(self, message: str | None = None, detail: str | None = None):
        self.user_message = message or self.user_message
        self.detail = detail
        super().__init__(self.user_message)


class InvalidFileError(AppError):
    status_code = 400
    user_message = "This file cannot be used. Please upload a valid PDF, PNG or JPG file."


class FileTooLargeError(AppError):
    status_code = 413
    user_message = "This file is larger than the allowed maximum size."


class DocumentNotFoundError(AppError):
    status_code = 404
    user_message = "This document is no longer available. It may have been removed."


class OllamaUnavailableError(AppError):
    status_code = 503
    user_message = (
        "Ollama is not running locally. Please start it with `ollama serve` and try again."
    )


class OllamaModelMissingError(AppError):
    status_code = 503
    user_message = (
        "Required Ollama model is not available. Please check the local Ollama model list."
    )


class AnswerGenerationError(AppError):
    status_code = 502
    user_message = "The answer could not be generated right now. Please try again."


class ReportGenerationError(AppError):
    status_code = 500
    user_message = "The report could not be created. Please try again."
