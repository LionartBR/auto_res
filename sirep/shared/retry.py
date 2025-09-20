from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
class TransientError(Exception): ...
retry3 = retry(
    retry=retry_if_exception_type(TransientError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=4)
)
