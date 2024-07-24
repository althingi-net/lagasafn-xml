#!/usr/bin/python
#
#  Polycat: A multi-file cat with context
#
#  Given a list of files and line numbers (filename:line), we print
#  those lines from the files, potentially with some added context.
#
import click
import os

@click.command()
@click.option('-b', '--before', default=0, help='Number of lines before', type=int)
@click.option('-a', '--after', default=0, help='Number of lines after', type=int)
@click.option('-f', '--show-filenames', is_flag=True, help='Show filenames before each line')
@click.option('-n', '--show-line-numbers', is_flag=True, help='Show line numbers before each line')
@click.option('-d', '--dir', default='.', help='Directory to search for files')
@click.argument('files', nargs=-1)
def polycat(before, after, files, dir, show_filenames, show_line_numbers):
    for file in files:
        filename, line = file.split(':')
        line = line.rstrip(',')     # Strip trailing commas if present
        line = int(line)
        full_filename = os.path.join(dir, filename)
        with open(full_filename) as f:
            lines = f.readlines()
            for i in range(max(0, line - before - 1), min(len(lines), line + after)):
                if show_filenames:
                    print(f"{filename}:", end='')
                if show_line_numbers:
                    print(f"{i + 1}:", end='')
                print(lines[i], end='')

        if before or after:
            print("--")


if __name__ == '__main__':
    polycat()
