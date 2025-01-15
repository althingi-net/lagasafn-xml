class LawException(Exception):
    pass


class ReferenceParsingException(LawException):
    pass


class NoSuchLawException(LawException):
    pass


class NoSuchElementException(LawException):
    pass


class AdvertParsingException(LawException):
    pass
