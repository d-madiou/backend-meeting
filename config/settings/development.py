from .base import *

DEBUG = True

# ======================================================================
# DEVELOPMENT-SPECIFIC SETTINGS
# ======================================================================

# Override default throttling rates for development to be more lenient.
# To completely disable throttling in development, set DEFAULT_THROTTLE_CLASSES to an empty list.
REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = []
# If you still want some throttling but very lenient, you can uncomment and adjust these rates:
# REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
#     'anon': '10000/minute',
#     'user': '50000/minute',
#     'messaging': '10000/minute',
# }
