import io
import json
import logging
import logging.config

import structlog
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils.module_loading import import_string
from structlog.testing import capture_logs

from tests.utils import PACKAGE, evaluate_settings

RequestMiddleware = import_string(f"{PACKAGE}.log_config.RequestMiddleware")


class LoggingSettingTest(SimpleTestCase):
    def test_json_outside_debug(self):
        logging_config = evaluate_settings(DEBUG="false")["LOGGING"]
        self.assertEqual(logging_config["handlers"]["console"]["formatter"], "json")

    def test_console_in_debug(self):
        logging_config = evaluate_settings(DEBUG="true")["LOGGING"]
        self.assertEqual(logging_config["handlers"]["console"]["formatter"], "console")

    def test_log_format_overrides_debug(self):
        logging_config = evaluate_settings(DEBUG="true", LOG_FORMAT="json")["LOGGING"]
        self.assertEqual(logging_config["handlers"]["console"]["formatter"], "json")

    def test_level_defaults_to_info(self):
        self.assertEqual(evaluate_settings()["LOGGING"]["root"]["level"], logging.INFO)

    def test_level_comes_from_the_environment(self):
        self.assertEqual(
            evaluate_settings(LOG_LEVEL="warning")["LOGGING"]["root"]["level"], logging.WARNING
        )

    def test_django_loggers_print_no_record_twice(self):
        # Django's default console handler on "django" would repeat every record in DEBUG.
        loggers = evaluate_settings(DEBUG="true")["LOGGING"]["loggers"]
        self.assertEqual(loggers["django"]["handlers"], [])

    def test_django_request_logs_only_errors(self):
        loggers = evaluate_settings()["LOGGING"]["loggers"]
        self.assertEqual(loggers["django.request"]["level"], "ERROR")

    def test_a_closed_stream_logs_at_debug(self):
        # A server-sent event stream ends when the browser leaves, which cancels its response.
        level = evaluate_settings()["DJANGO_STRUCTLOG_REQUEST_CANCELLED_LOG_LEVEL"]
        self.assertEqual(level, logging.DEBUG)

    def test_client_addresses_are_not_logged(self):
        self.assertIs(evaluate_settings()["DJANGO_STRUCTLOG_IP_LOGGING_ENABLED"], False)


class RequestLoggingTest(TestCase):
    def test_capture_logs_sees_requests_after_the_settings_ran_again(self):
        # The first request caches django-structlog's logger with the processor list of that time.
        self.client.get("/missing/")
        evaluate_settings()
        with capture_logs() as logs:
            self.client.get("/missing/")
        self.assertIn("request_finished", [log["event"] for log in logs])

    def test_the_line_shows_the_redirect_that_goes_out(self):
        # CommonMiddleware turns the 404 of /admin into a 301 to /admin/ under APPEND_SLASH.
        with capture_logs() as logs:
            response = self.client.get("/admin")
        self.assertEqual(response.status_code, 301)
        finished = [log for log in logs if log["event"] == "request_finished"]
        self.assertEqual([log["code"] for log in finished], [301])

    def test_successful_requests_leave_no_line_at_info(self):
        with capture_logs() as logs:
            self.client.get("/health/other")  # a 404 to compare with below
            self.client.get("/admin/login/?next=/admin/")
        finished = [log for log in logs if log["event"] == "request_finished"]
        levels = {log["code"]: log["log_level"] for log in finished}
        self.assertEqual(levels[200], "debug")
        self.assertEqual(levels[404], "warning")

    def test_request_line_has_no_query_string_or_user_agent(self):
        with capture_logs() as logs:
            self.client.get("/missing/?token=secret", headers={"user-agent": "Probe/1.0"})
        lines = [log for log in logs if log["event"] in ("request_started", "request_finished")]
        self.assertEqual(len(lines), 2)
        for log in lines:
            self.assertEqual(log["request"], "GET /missing/")
            self.assertNotIn("user_agent", log)
            self.assertNotIn("ip", log)

    def test_failed_request_line_has_no_query_string(self):
        middleware = RequestMiddleware(lambda request: HttpResponse())
        request = RequestFactory().get("/boom/?token=secret")
        with capture_logs() as logs:
            middleware._process_exception(request, ValueError("boom"))
        failed = [log for log in logs if log["event"] == "request_failed"]
        self.assertEqual([log["request"] for log in failed], ["GET /boom/"])


class JsonOutputTest(SimpleTestCase):
    def last_json_line(self, emit) -> dict:
        """The JSON line that `emit` writes under the production LOGGING."""
        config = evaluate_settings(DEBUG="false")["LOGGING"]
        stream = io.StringIO()
        config["handlers"]["console"]["stream"] = stream
        previous = logging.getLogger().handlers[:]
        try:
            logging.config.dictConfig(config)
            emit()
        finally:
            structlog.contextvars.clear_contextvars()
            logging.getLogger().handlers[:] = previous
        return json.loads(stream.getvalue().strip().splitlines()[-1])

    def test_a_standard_library_record_carries_the_bound_request_id(self):
        def emit():
            structlog.contextvars.bind_contextvars(request_id="r-1")
            logging.getLogger(f"{PACKAGE}.probe").warning("feed refresh failed")

        line = self.last_json_line(emit)
        self.assertEqual(line["event"], "feed refresh failed")
        self.assertEqual(line["level"], "warning")
        self.assertEqual(line["request_id"], "r-1")
        self.assertEqual(line["logger"], f"{PACKAGE}.probe")
        self.assertIn("timestamp", line)

    def test_a_request_passed_as_extra_shows_no_query_string(self):
        # django.request and django.security pass the request object along with their records.
        request = RequestFactory().get("/missing/?token=secret")
        line = self.last_json_line(
            lambda: logging.getLogger("django.security.csrf").warning(
                "Forbidden", extra={"request": request}
            )
        )
        self.assertEqual(line["request"], "GET /missing/")
