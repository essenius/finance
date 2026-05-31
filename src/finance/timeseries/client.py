from .errors import TimeSeriesError
from .influx import InfluxBackend


class TimeSeriesClient:
    def __init__(self, secrets):
        self.backend = InfluxBackend(secrets)

    def write(self, bucket, measurement, fields, tags, timestamp):
        try:
            return self.backend.write(bucket, measurement, fields, tags, timestamp)
        except Exception as e:
            raise TimeSeriesError(str(e)) from None

    def read(self, bucket, measurement, start, stop):
        try:
            return self.backend.read(bucket, measurement, start, stop)
        except Exception as e:
            raise TimeSeriesError(str(e)) from None
