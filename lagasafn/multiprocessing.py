import os
import signal
from lagasafn import settings
from multiprocessing.pool import Pool
from multiprocessing import get_context

"""
A tailor-made `Pool` for our project, so that we can re-use it with the same
setup in multiple places without repeating the boilerplate.

It also respects the `--single-thread` option, so that debugging can be used
when needed. It will respect Ctrl-C.

Usage, where `process_law` takes a single argument `law_id`:

    law_ids = [
        1,
        2,
        3,
    ]

    with CustomPool() as pool:

        results = pool.run(process_law, law_ids)

        while True:
            try:
                result = next(results)

                print("Result: %s" % result)

            except StopIteration:
                break
"""

def init_pool():
    # Start ignoring the KeyboardInterrupt signal in the main thread. The
    # result is that it gets caught by the sub-processes, which **don't**
    # inherit this setting. The exception is then thrown when waiting for
    # the process pool to finish, and caught by the code running the
    # `main` function.
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def yieldify_function(function, arguments):
    """
    Multiprocessing has some wide-reaching implications for various
    under-the-hood mechanics like debugging. We need the ability to have those
    work, so we offer this option to sidestep threading.

    This is only "yield-ified" so that the results stay compatible with the
    code that handles those same results when using multiprocessing.
    """
    for argument in arguments:
        yield function(argument)


class CustomPool(Pool):
    """
    A custom `Pool` class that works accordig to project-specific expectations.
    """
    def __init__(self, processes=None, initializer=None, initargs=(), maxtasksperchild=None, context=None):

        if processes is None:
            # This is apparently safer than `multiprocessing.cpu_count()`,
            # according to:
            # https://stackoverflow.com/questions/1006289/how-to-find-out-the-number-of-cpus-using-python
            processes = len(os.sched_getaffinity(0))

        if initializer is None:
            initializer = init_pool

        if context is None:
            context = get_context()

        super().__init__(processes, initializer, initargs, maxtasksperchild, context)

    def run(self, function, arguments):
        if "--single-thread" in settings.options and settings.options["--single-thread"] == True:
            return yieldify_function(function, arguments)
        else:
            return self.imap_unordered(function, arguments)
