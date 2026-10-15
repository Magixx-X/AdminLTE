class QueryProvider:
    def rows(self, version, params, month, scopes, stop, timeout):
        """Yield (column names, row tuple), bounded streaming, or raise on cancellation."""
        raise NotImplementedError

    def health(self):
        raise NotImplementedError


class QueryCancelled(Exception):
    pass


class QueryTimeout(Exception):
    pass
