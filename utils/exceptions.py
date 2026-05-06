class Error(Exception):
    """Lớp ngoại lệ cơ bản, các ngoại lệ khác sẽ kế thừa lớp này"""

    def __init__(self, status_code=None):
        self.status_code = status_code
        print(
            "Chương trình gặp lỗi, vui lòng kiểm tra thông tin lỗi."
        )

    def display_error(self):
        """Hiển thị thông tin lỗi và mã trạng thái (nếu có)"""
        return f"Lỗi: {self.args[0]}." + (
            f" Mã trạng thái: {self.status_code}." if self.status_code else ""
        )


class ConnectionError(Error):
    """Ném ra khi có vấn đề về kết nối"""

    def display_error(self):
        return f" Lỗi kết nối: {self.args[0]}."


class UnavailableError(Error):
    """Ném ra khi dịch vụ không khả dụng, ví dụ: bảo trì hoặc quá tải"""

    def display_error(self):
        return f" Lỗi dịch vụ không khả dụng: {self.args[0]}."


class NotFoundError(Error):
    """Ném ra khi địa chỉ truy cập (endpoint) không tồn tại"""

    def display_error(self):
        return f" Lỗi không tìm thấy (404): {self.args[0]}."


class ResponseError(Error):
    """Ném ra khi phản hồi trả về không đúng như mong đợi"""

    def display_error(self):
        return f" Lỗi phản hồi (Response): {self.args[0]}."


class RateLimitError(Error):
    """Ném ra khi vượt quá giới hạn số lượng yêu cầu (Rate Limit)"""

    def display_error(self):
        return f" Lỗi giới hạn lượt truy cập: {self.args[0]}."


class TimeoutError(Error):
    """Ném ra khi yêu cầu bị quá hạn thời gian (Timeout)"""

    def display_error(self):
        return f" Lỗi quá hạn thời gian: {self.args[0]}."


class UnauthorizedError(Error):
    """Ném ra khi yêu cầu bị từ chối do lỗi xác thực hoặc không có quyền"""

    def display_error(self):
        return f" Lỗi chưa xác thực/không có quyền: {self.args[0]}."


class RetryExhaustedError(Error):
    """Ném ra khi đã thử lại tối đa số lần cho phép nhưng vẫn thất bại"""

    def display_error(self):
        return f" Lỗi đã hết lượt thử lại: {self.args[0]}."
