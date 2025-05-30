class LawException(Exception):
    pass

class BillException(Exception):
    pass


class ReferenceParsingException(LawException):
    pass


class NoSuchLawException(LawException):
    pass


class NoSuchElementException(LawException):
    pass


class AdvertException(Exception):
    pass


class AdvertParsingException(AdvertException):
    pass


class IntentParsingException(Exception):
    pass
