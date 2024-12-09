import os
from lagasafn import diff_patch_utils
from lagasafn import settings
from lagasafn.constants import PATCH_FILENAME
from lagasafn.constants import PATCHED_FILENAME
from lagasafn.constants import PATCHES_BASE_DIR
from lagasafn.constants import CLEAN_FILENAME
from shutil import copy
from subprocess import DEVNULL
from subprocess import run


def patch_law(law_num, law_year) -> bool:

    patch_path = os.path.join(PATCH_FILENAME % (law_year, law_num))
    if not os.path.isfile(patch_path):

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


def auto_patch(law_num, law_year):
    # Nevermind if the patch already exists.
    patch_path = os.path.join(PATCH_FILENAME % (law_year, law_num))
    if os.path.isfile(patch_path):
        return

    # Scan for available patched parliaments.
    parliament_dir = os.path.dirname(os.path.dirname(patch_path))
    patched_parliaments = []
    for item in os.listdir(parliament_dir):
        if os.path.isdir(os.path.join(parliament_dir, item)):
            patched_parliaments.append(item)

    # We rely on sorting to properly locating previous and next parliaments.
    patched_parliaments.sort()

    # This is a list because when we start iterating backwards, we'll want to try both patches 
    previous_parliament = patched_parliaments[patched_parliaments.index(settings.CURRENT_PARLIAMENT_VERSION) - 1]

    attempt_patch_transfer(law_num, law_year, previous_parliament)


def attempt_patch_transfer(law_num, law_year, previous_parliament):
    filename = CLEAN_FILENAME % (law_year, law_num)
    attempted_patch = os.path.join(PATCHES_BASE_DIR, previous_parliament, "%d-%d.html.patch" % (law_year, law_num))
    target_patch = PATCHED_FILENAME % (law_year, law_num)
    patch_filename = PATCH_FILENAME % (law_year, law_num)

    if not os.path.isfile(attempted_patch):
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
