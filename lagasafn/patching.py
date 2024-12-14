import os
from lagasafn import diff_patch_utils
from lagasafn import settings
from lagasafn.constants import CLEAN_FILENAME
from lagasafn.constants import PATCH_FILENAME
from lagasafn.constants import PATCHED_FILENAME
from lagasafn.constants import PATCHES_BASE_DIR
from lagasafn.constants import JSON_MAP_BASE_DIR
from lagasafn.constants import XML_BASE_DIR
from lagasafn.settings import CURRENT_PARLIAMENT_VERSION
from os.path import isfile
from os.path import join
from shutil import copy
from subprocess import DEVNULL
from subprocess import run


def patch_law(law_num, law_year) -> bool:

    patch_path = os.path.join(PATCH_FILENAME % (law_year, law_num))
    if not isfile(patch_path):

        # Auto-patch if requested.
        if "--auto-patch" in settings.options:
            auto_patch(law_num, law_year)

        return False

    if not os.path.isdir(os.path.dirname(PATCHED_FILENAME)):
        os.mkdir(os.path.dirname(PATCHED_FILENAME))

    filename = CLEAN_FILENAME % (law_year, law_num)
    patch_path = os.path.join(PATCH_FILENAME % (law_year, law_num))
    patched_content = diff_patch_utils.do_patch(filename, patch_path)
    with open(PATCHED_FILENAME % (law_year, law_num), "w") as patched_file:
        patched_file.write(patched_content)

    return True


def get_other_parliament(iteration: int):

    # Scan for available patched parliaments.
    patched_parliaments = []
    for item in os.listdir(XML_BASE_DIR):
        if os.path.isdir(os.path.join(XML_BASE_DIR, item)):
            patched_parliaments.append(item)

    # We rely on sorting to properly locating previous and next parliaments.
    patched_parliaments.sort()

    # This is a list because when we start iterating backwards, we'll want to try both patches 
    try:
        other_parliament = patched_parliaments[patched_parliaments.index(settings.CURRENT_PARLIAMENT_VERSION) + iteration]
        return other_parliament
    except IndexError:
        return None


def auto_patch(law_num, law_year):
    # Nevermind if the patch already exists.
    patch_path = os.path.join(PATCH_FILENAME % (law_year, law_num))
    if isfile(patch_path):
        return

    previous_parliament = get_other_parliament(-1)

    # First try the patch from the previous parliament, but if that doesn't
    # work, then try the one from the next parliament.
    if not attempt_patch_transfer(law_num, law_year, previous_parliament):
        next_parliament = get_other_parliament(1)
        if next_parliament is not None:
            attempt_patch_transfer(law_num, law_year, next_parliament)


def attempt_patch_transfer(law_num, law_year, previous_parliament):
    # NOTE: This rewquires GNU `diff` and `patch`, which should be
    # available on any modern operating systems, except Windows.
    filename = CLEAN_FILENAME % (law_year, law_num)
    attempted_patch = os.path.join(PATCHES_BASE_DIR, previous_parliament, "%d-%d.html.patch" % (law_year, law_num))
    target_patch = PATCHED_FILENAME % (law_year, law_num)
    patch_filename = PATCH_FILENAME % (law_year, law_num)

    if not isfile(attempted_patch):
        return False

    result = run(["patch", "--dry-run", filename, attempted_patch], stdout=DEVNULL)
    if result.returncode == 0:
        # Apply the patch.
        copy(filename, target_patch)
        run(["patch", target_patch, attempted_patch], stdout=DEVNULL)

        # Create a new one, based on the cleaned file from the current parliament.
        with open(patch_filename, "w") as f:
            result = run(["diff", "-U10", filename, target_patch], stdout=f)
            if result.returncode == 0:
                return True

    return False


def attempt_json_map_transfer():
    previous_parliament = get_other_parliament(-1)

    json_files = [
        "errormap.json",
        "straytextmap.json",
        "splitmap.json",
    ]

    for json_file in json_files:
        previous_path = join(JSON_MAP_BASE_DIR, previous_parliament, json_file)
        current_path = join(JSON_MAP_BASE_DIR, CURRENT_PARLIAMENT_VERSION, json_file)

        if not isfile(current_path):
            copy(previous_path, current_path)
