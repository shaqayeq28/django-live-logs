import os
import re
from fnmatch import fnmatch
from itertools import islice

from django.contrib.admin.utils import quote, unquote
from django.http import JsonResponse

from . import settings


def get_log_files(directory, max_items_per_page, current_page):
    """
    Function to get the logs file names.
    :param `directory` is string of base logs path.
    :param `max_items_per_page` is int max items to show per-page.
    :param `current_page` is int of current page.
    :return dict of logs files data.
    >>> get_log_files("logs", 2, 1)
    {
      "logs": {
        "": [
          "default.log",
          "request_debug.log",
          "request_error.log"
        ]
      },
      "next_page_files": 2,
      "last_files": false
    }
    >>>
    """
    result = {}
    all_log_files = []
    for root, _, files in os.walk(directory):
        all_files = list(filter(lambda x: x.find("~") == -1, files))

        all_log_files.extend(list(filter(lambda x: x in settings.LOG_VIEWER_FILES, all_files)))
        all_log_files.extend([x for x in all_files if fnmatch(x, settings.LOG_VIEWER_FILES_PATTERN)])
        log_dir = os.path.relpath(root, directory)
        if log_dir == ".":
            log_dir = ""

        result["logs"] = {log_dir: list(set(all_log_files))}
        result["next_page_files"] = current_page + 1
        result["last_files"] = (all_log_files.__len__() <= current_page * max_items_per_page)

    return result


def readlines_reverse(qfile, exclude=None):
    """
    Read file lines from bottom to top
    :param `qfile` is queue read file, i.e: with open(..., 'r') as qfile:
    :param `exclude` is string regex expression to exclude the log from line.
    :return yield string
    """
    # support custom patterns (fixed issue #4)
    patterns = settings.LOG_VIEWER_PATTERNS
    reversed_patterns = [x[::-1] for x in patterns]

    qfile.seek(0, os.SEEK_END)
    position = qfile.tell()
    line = ""

    while position >= 0:
        qfile.seek(position)
        next_char = qfile.read(1)

        # original
        # exclude = ""  # in param
        # if next_char == "\n" and line and line[-1] == '[':
        #     if exclude in line[::-1]:
        #         line = ''
        #     else:
        #         yield line[::-1]
        #         line = ''
        # else:
        #     line += next_char

        # modified
        if next_char == "\n" and line:
            if any([line.endswith(p) for p in reversed_patterns]):
                if exclude and re.search(exclude, line[::-1]).group(0):
                    line = ""
                else:
                    yield line[::-1]
                    line = ""
        else:
            line += next_char
        position -= 1
    yield line[::-1]


class JSONResponseMixin:
    """
    A mixin that can be used to render a JSON response.
    """

    def render_to_json_response(self, context, **response_kwargs):
        """
        Returns a JSON response, transforming 'context' to make the payload.
        """
        return JsonResponse(self.get_data(context), **response_kwargs)

    def get_data(self, context):
        """
        Returns an object that will be serialized as JSON by json.dumps().
        """
        # Note: This is *EXTREMELY* naive; in reality, you'll need
        # to do much more complex handling to ensure that arbitrary
        # objects -- such as Django model instances or querysets
        # -- can be serialized as JSON.
        return context


def get_log_entries_context(original_context=None):
    if not original_context:
        original_context = {}

    context = {}
    page = original_context.get('page', 1)
    file_name = original_context.get('file_name', '')

    # Clean the `file_name` to avoid relative paths.
    file_name = unquote(file_name).replace('/..', '').replace('..', '')
    page = int(page)
    current_file = file_name

    lines_per_page = settings.LOG_VIEWER_MAX_READ_LINES
    context['original_file_name'] = file_name
    context['next_page'] = page + 1
    context['log_files'] = []

    log_file_data = get_log_files(settings.LOG_VIEWER_FILES_DIR, settings.LOG_VIEWER_FILE_LIST_MAX_ITEMS_PER_PAGE, 1, )
    context['next_page_files'] = log_file_data['next_page_files']
    context['last_files'] = log_file_data['last_files']

    for log_dir, log_files in log_file_data['logs'].items():
        for log_file in log_files:
            display = os.path.join(log_dir, log_file)
            uri = os.path.join(settings.LOG_VIEWER_FILES_DIR, display)

            context['log_files'].append({quote(display): {'uri': uri, 'display': display, }})

    if file_name:
        try:
            file_log = os.path.join(settings.LOG_VIEWER_FILES_DIR, file_name)
            with open(file_log, encoding='utf8', errors='ignore') as file:
                next_lines = list(islice(readlines_reverse(file, exclude=settings.LOG_VIEWER_EXCLUDE_TEXT_PATTERN),
                                         (page - 1) * lines_per_page, page * lines_per_page, ))

                if len(next_lines) < lines_per_page:
                    context['last'] = True
                else:
                    context['last'] = False
                context['logs'] = next_lines
                context['current_file'] = current_file
                context['file'] = file

        except Exception as error:
            print(error)
            pass
    else:
        context['last'] = True

    if len(context['log_files']) > 0:
        context['log_files'] = sorted(context['log_files'], key=lambda x: sorted(x.items()))

    return context


def reverse_readlines(file, exclude=None):
    patterns = settings.LOG_VIEWER_PATTERNS
    reversed_patterns = [x[::-1] for x in patterns]

    file.seek(0, os.SEEK_END)
    position = file.tell()
    line = ""

    while position >= 0:
        file.seek(position)
        next_char = file.read(1)

        if next_char == "\n" and line:
            if any([line.endswith(p) for p in reversed_patterns]):
                if exclude and re.search(exclude, line[::-1]).group(0):
                    line = ""
                else:
                    yield line[::-1]
                    line = ""
        else:
            line += next_char

        position -= 1

    yield line[::-1]


def get_log_entries(filename):
    file_log = os.path.join(settings.LOG_VIEWER_FILES_DIR, filename)
    with open(file_log, encoding='utf8', errors='ignore') as file:
        log_entries = list(islice(reverse_readlines(file, exclude=settings.LOG_VIEWER_EXCLUDE_TEXT_PATTERN), 1000))

    return log_entries
