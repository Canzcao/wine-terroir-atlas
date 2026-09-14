from datetime import tzinfo, timedelta

class ZoneInfo(tzinfo):
    def __init__(self, key='UTC'):
        self._key = key

    def utcoffset(self, dt):
        return timedelta(hours=8) if self._key == 'Asia/Shanghai' else timedelta(0)

    def dst(self, dt):
        return timedelta(0)

    def tzname(self, dt):
        return 'Asia/Shanghai' if self._key == 'Asia/Shanghai' else 'UTC'
