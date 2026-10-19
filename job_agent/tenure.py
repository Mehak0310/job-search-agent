"""Conservative tenure from approved month-precision dates; never round up."""
import calendar
from datetime import date


def tenure_bounds(start_month: str, as_of: date):
    year, month = map(int, start_month.split('-'))
    earliest=date(year,month,1)
    latest=date(year,month,calendar.monthrange(year,month)[1])
    def elapsed(start):
        months=(as_of.year-start.year)*12+as_of.month-start.month-(as_of.day<start.day)
        return max(0,months)
    return {'minimum_complete_months':elapsed(latest),'maximum_complete_months':elapsed(earliest),
            'as_of':as_of.isoformat(),'start_precision':'month'}
