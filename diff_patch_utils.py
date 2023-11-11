#!/usr/bin/python
import argparse
import datetime
import difflib
import os
import pathlib
import re
import sys
import typing

"""unified diff/patch utilities for python3

Contains set of utility functions that provide diff/patch functionality in python, the diff format
is unified diff and by default the so-called -U0 (or --unidiff-zero) format, which you can get from
GNU diffutils like so:

    $ diff -U0 a.txt b.txt

and the patch functionality assumes this unified diff format as input.

Note that the 0 in -U0 decides how many additional lines for context before and after changed lines
to include in diff file for good safety measures, in some usecases it can be argued it's fine to
include no additional lines for context, though in other cases like when using git apply it's
officially discouraged and obstructed yet bypassable using the --unidiff-zero flag.

Diff unified format provided by the standard python library difflib.

Patch implemented in pure python. Assumes comments in lines starting with "#".
"""


class BadPatch(Exception):
    pass


def do_diff_str(input_a: str, input_b: str, context: int = 0) -> str:
    """
    Get unified string diff between two strings.
    Returns empty string if strings are identical.
    """
    no_eol = "\\ No newline at end of file"
    diffs = difflib.unified_diff(
        input_a.splitlines(True), input_b.splitlines(True), n=context
    )
    try:
        _, _ = next(diffs), next(diffs)  # trim top two header lines
    except StopIteration:
        pass
    return "".join([d if d[-1] == "\n" else d + "\n" + no_eol + "\n" for d in diffs])


def do_diff(
    filename_a: str,
    filename_b: str,
    a_encoding: str = "utf-8",
    b_encoding: str = "utf-8",
    headers: bool = True,
    context: int = 0,
) -> str:
    """
    Get unified string diff between contents of two files.
    Writes filenames and modified timestamps to header lines.
    Returns empty string if strings are identical.
    """
    fname_a = pathlib.Path(filename_a)
    fname_b = pathlib.Path(filename_b)
    assert fname_a.exists() and fname_a.is_file(), f"No such file: {fname_a}"
    assert fname_b.exists() and fname_b.is_file(), f"No such file: {fname_b}"
    ts_format = "%Y-%m-%d %H:%M:%S.%f"
    # Note: we assume pathlib.Path().stat() to have POSIX timestamps (hence tz being utc), however
    # this unfortunately varies between operating systems
    tz_utc = datetime.timezone.utc
    a_mod_ts_ns = fname_a.stat().st_mtime_ns
    b_mod_ts_ns = fname_b.stat().st_mtime_ns
    a_mod_ts = datetime.datetime.fromtimestamp(a_mod_ts_ns / 1e9, tz=tz_utc)
    b_mod_ts = datetime.datetime.fromtimestamp(b_mod_ts_ns / 1e9, tz=tz_utc)
    diff = ""
    with open(filename_a, "r", encoding=a_encoding) as file_a:
        input_a_str = file_a.read()
        with open(filename_b, "r", encoding=b_encoding) as file_b:
            input_b_str = file_b.read()
            diff += do_diff_str(input_a_str, input_b_str, context)
    if headers is True and diff != "":
        diff = (  # add header lines
            "--- {filename_a}\t{a_modified_ts} +0000\n"
            "+++ {filename_b}\t{b_modified_ts} +0000\n"
            "{diff}"
        ).format(
            filename_a=filename_a,
            filename_b=filename_b,
            a_modified_ts="{}{:03.0f}".format(
                a_mod_ts.strftime(ts_format), a_mod_ts_ns % 1e3
            ),
            b_modified_ts="{}{:03.0f}".format(
                b_mod_ts.strftime(ts_format), b_mod_ts_ns % 1e3
            ),
            diff=diff,
        )
    return diff


def do_patch_str(contents: str, patch: str, revert: bool = False) -> str:
    """
    Apply @patch to @contents and return patched string.
    If revert is True, treat @contents as the patched string, recover unpatched string.
    """
    hdr_pat = re.compile(r"^@@ -(\d+),?(\d+)? \+(\d+),?(\d+)? @@$")
    input_lines = contents.splitlines(True)
    patch_lines = patch.splitlines(True)
    output = ""
    pl_i = 0  # patch_line counter
    il_i = 0  # input_line counter
    (midx, sign) = (1, "+") if not revert else (3, "-")
    while pl_i < len(patch_lines) and patch_lines[pl_i].startswith(("#", "---", "+++")):
        pl_i += 1  # skip comments and file info header lines
    while pl_i < len(patch_lines):
        hunk_match = hdr_pat.match(patch_lines[pl_i])
        if hunk_match is None:
            raise BadPatch('Bad patch -- regex mismatch [patch line "%s"]' % (pl_i,))
        h_l = (
            int(hunk_match.group(midx)) - 1 + (hunk_match.group(midx + 1) == "0")
        )  # hunk line nr
        if il_i > h_l or h_l > len(input_lines):
            raise BadPatch('Bad patch -- bad line num [patch line "%s"]' % (pl_i,))
        output += "".join(input_lines[il_i:h_l])
        il_i = h_l
        pl_i += 1
        while pl_i < len(patch_lines) and patch_lines[pl_i][0] != "@":
            cur_pl_i = pl_i
            if pl_i + 1 < len(patch_lines) and patch_lines[pl_i + 1][0] == "\\":
                # for fulfilling newline skipping at the end of file
                # see variable "no_eol" in function "do_diff_str"
                line = patch_lines[pl_i][:-1]
                pl_i += 2
            else:
                line = patch_lines[pl_i]
                pl_i += 1
            if len(line) > 0:
                if line[0] not in ("+", "-", " ", "#", "\\"):
                    raise BadPatch(
                        'Bad patch -- unexptected start of line [patch line "%s"]'
                        % (cur_pl_i,)
                    )
                if line[0] != sign and line[0] in ("+", "-", " "):
                    # safety checks: make sure input string and patch string match up
                    if input_lines[il_i] != line[1:]:
                        raise BadPatch(
                            (
                                "Bad patch -- input and patch mismatch "
                                '[input line "%s", patch line "%s"]'
                            )
                            % (il_i, cur_pl_i)
                        )
                if line[0] == sign or line[0] == " ":
                    output += line[1:]
                if line[0] not in (sign, "#"):
                    # the '#' is for ignoring commented lines in patch file which is recognizable
                    # by for example GNU patch
                    # note that some patch tools like for example 'git apply' might see these '#'
                    # styled comments as a corrupt patch file
                    il_i += 1

    output += "".join(input_lines[il_i:])
    return output


def do_patch(
    filename: str,
    patch_filename: str,
    f_encoding: str = "utf-8",
    p_encoding: str = "utf-8",
    revert: bool = False,
) -> str:
    """
    Apply patch file to file contents and only return patched string.
    If revert is True, treat file contents as after patch, recover file contents before patch.
    """
    fname = pathlib.Path(filename)
    fname_patch = pathlib.Path(patch_filename)
    assert os.path.isfile(fname), f"No such file: {fname}"
    assert os.path.isfile(fname_patch), f"No such file: {fname_patch}"
    output = ""
    with open(filename, "r", encoding=f_encoding) as file:
        file_str = file.read()
        with open(patch_filename, "r", encoding=p_encoding) as patch_file:
            patch_file_str = patch_file.read()
            output = do_patch_str(file_str, patch_file_str, revert)
    return output


def main(args: typing.Dict) -> None:
    if "context" in args:
        context = args["context"]
    else:
        context = 0
    if args["make-patch"] is True:
        diff_content = do_diff(args["file-a"], args["file-b"], context=context)
        with open(args["output-file"], "w") as output_file:
            output_file.write(diff_content)


if __name__ == "__main__":
    argparser = argparse.ArgumentParser(
        description="Diff Patch Utils",
        formatter_class=argparse.RawTextHelpFormatter,
        prog="diff-patch-utils",
    )
    argparser.add_argument(
        "-mp",
        "--make-patch",
        action="store_true",
        help=("Take diff of two files and create a patch file."),
    )
    argparser.add_argument(
        "-fa", "--file-a", metavar=("FILE_A",), help=("Input file A.")
    )
    argparser.add_argument(
        "-fb", "--file-b", metavar=("FILE_B",), help=("Input file B.")
    )
    argparser.add_argument(
        "-c",
        "--context",
        type=int,
        default=0,
        metavar=("CONTEXT",),
        help=("Diff context, integer >= 0 (default: 0)."),
    )
    argparser.add_argument(
        "-o", "--output-file", metavar=("OUTPUT_FILE",), help=("Output file.")
    )
    if len(sys.argv) == 1:
        argparser.print_help(sys.stderr)
    pargs = argparser.parse_args()
    args = {
        "make-patch": pargs.make_patch,
        "file-a": pargs.file_a,
        "file-b": pargs.file_b,
        "context": pargs.context,
        "output-file": pargs.output_file,
    }
    assert args["context"] >= 0, "context should be >= 0"
    main(args)
