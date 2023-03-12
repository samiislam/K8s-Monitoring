import logging
import requests

from flask import Flask, jsonify
from flask_opentracing import FlaskTracing
from jaeger_client import Config
from jaeger_client.metrics.prometheus import PrometheusMetricsFactory
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)
RequestsInstrumentor().instrument()

metrics = PrometheusMetrics(app)
# static information as metric
metrics.info("app_info", "Python Flask Application", version="1.0.0")

logging.getLogger("").handlers = []
logging.basicConfig(format="%(message)s", level=logging.DEBUG)
logger = logging.getLogger(__name__)


def init_tracer(service):

    config = Config(
        config={
            "sampler": {"type": "const", "param": 1},
            "logging": True,
            "reporter_batch_size": 1,
        },
        service_name=service,
        validate=True,
        metrics_factory=PrometheusMetricsFactory(service_name_label=service),
    )

    # this call also sets opentracing.tracer
    return config.initialize_tracer()


tracer = init_tracer("python")
flask_tracer = FlaskTracing(tracer, True, app)


@app.route("/")
def homepage():
    return jsonify(result="Hello World from Python Flask")


@app.route("/create40x")
def create40x():
    return ("40x error", 404)


@app.route("/create50x")
def create50x():
    return ("50x error", 501)


@app.route("/pythonbooks")
def get_python_books():
    url = 'http://openlibrary.org/subjects/python?limit=20'
    headers = {'Accept': 'application/json'}

    book_details = []

    with tracer.start_active_span('get-python-books') as scope:
        res = requests.get(url, headers=headers)
        scope.span.set_tag('http.status_code', res.status_code)
        res_json = res.json()

        books_count = res_json['work_count']
        scope.span.set_tag('books-count', books_count)
        scope.span.log_kv({'event': 'get books count',
                          'count': books_count})

        for num, book in enumerate(res_json['works']):
            title, description = get_book_details(num, book)
            book_details.append({'title': title, 'description': description})

    return jsonify(book_details)


def get_book_details(num, book):
    headers = {'Accept': 'application/json'}

    title = book['title']
    key = book['key']
    url = 'http://openlibrary.org' + key

    with tracer.start_active_span('get-book-details') as scope:
        res = requests.get(url, headers=headers)
        scope.span.set_tag('http.status_code', res.status_code)
        res_json = res.json()

        description = res_json[
            'description'] if 'description' in res_json else 'No description available'

        scope.span.log_kv({'event': 'get book details', 'details': {
                          'title': title, 'description': description}})

    return title, description


if __name__ == "__main__":
    app.run()
