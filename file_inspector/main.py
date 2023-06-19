import math
import os
import pathlib
import shutil
import tempfile

import click
import watchfiles
from diff_match_patch import diff_match_patch


def print_event_message(change: watchfiles.Change, path: pathlib.Path) -> None:
    """Prints a comprehensive message of what event occurred."""
    if change is watchfiles.Change.added:
        if path.is_file():
            click.secho(f'File {path} added', fg='green')
        else:
            click.secho(f'Folder {path} added', fg='green')
    elif change is watchfiles.Change.deleted:
        # We can't use path.is_file() here since the file / folder doesn't exist anymore :D
        # So a best-try is to check for a suffix, if there is one, we consider it a file
        # if not, it is folder
        if path.suffix:
            click.secho(f'File {path} deleted', fg='yellow')
        else:
            click.secho(f'Folder {path} deleted', fg='yellow')
    else:
        # We don't bother with folder modification since it is not relevant of what change really happen
        if path.is_file():
            click.secho(f'File {path} modified', fg='blue')


def get_temp_path(file_path: pathlib.Path, monitored_folder: pathlib.Path, temp_dir: str) -> pathlib.Path:
    common_path = os.path.commonpath([file_path, monitored_folder])
    str_file = str(file_path)
    path_suffix = str_file[len(common_path):]
    return pathlib.Path(temp_dir + path_suffix)


def print_file_differences(previous_text: str, current_text: str) -> None:
    dmp = diff_match_patch()
    patches = dmp.patch_make(previous_text, current_text)
    for patch in patches:
        line = str(patch)
        if line.startswith('@'):
            click.secho(line, fg='cyan')
        elif line.startswith('-'):
            click.secho(line, fg='red')
        elif line.startswith('+'):
            click.secho(line, fg='green')
        else:
            click.echo(f'{line}\n')


def rsync_and_diff(
        change: watchfiles.Change, path: pathlib.Path, monitored_folder: pathlib.Path, temp_dir: str
) -> None:
    """
    Synchronizes files from monitored folder to the temporary folder.
    For a file modification event, prints the difference between the previous and the current version.
    """
    temp_path = get_temp_path(path, monitored_folder, temp_dir)
    if change is watchfiles.Change.added:
        if path.is_file():
            # when you create a folder with files, it is possible that the file event comes before the folder
            # event, so you don't have the folder already existing, we need to be sure to have it first
            parent = temp_path.parent
            parent.mkdir(exist_ok=True)
            temp_path.write_text(path.read_text())
        else:
            shutil.copytree(path, temp_path, dirs_exist_ok=True)
    elif change is watchfiles.Change.modified:
        if path.is_file():
            current_version = path.read_text()
            print_file_differences(temp_path.read_text(), current_version)
            temp_path.write_text(current_version)
    else:
        if temp_path.is_dir():
            shutil.rmtree(temp_path, ignore_errors=True)
        else:
            temp_path.unlink(missing_ok=True)


def get_human_readable_size(size: int) -> str:
    """Converts a file size in bytes to a human-readable format."""
    units = ['B', 'KB', 'MB', 'GB', 'TB']

    if size == 0:
        return '0 B'

    # Calculate the exponent (base 1024) of the appropriate unit
    exponent = min(int(math.log(size, 1024)), len(units) - 1)

    # Calculate the size in the appropriate unit
    size /= 1024 ** exponent

    # Format the size with a maximum of two decimal places
    size_str = f'{size:.2f}'

    # Remove trailing zeros and the decimal point if the number is an integer
    size_str = size_str.rstrip('0').rstrip('.') if '.' in size_str else size_str

    return f'{size_str} {units[exponent]}'


def print_folder_size(folder: pathlib.Path, size: int) -> None:
    size_message = click.style(get_human_readable_size(size), fg='blue')
    click.echo(f'\nTotal size of {folder}: {size_message}\n')


@click.argument('folder', type=click.Path(file_okay=False), default='.')
@click.command()
def cli(folder: str):
    """
    Inspects the FOLDER passed as parameter and give the following information:

    \b
    - file / folder created / updated / deleted
    - total size of the watched folder
    - In case of updated file, the diff between previous version and current version

    \b
    Examples
    $ inspector .  # current folder
    $ inspector /path/to/folder/to/watch
    """
    monitored_folder = pathlib.Path(folder).absolute()
    click.echo(f'monitoring folder {click.style(monitored_folder, fg="blue")}...')

    with tempfile.TemporaryDirectory() as temp_dir:
        # we create a copy of the monitored folder
        shutil.copytree(folder, temp_dir, dirs_exist_ok=True)

        for changes in watchfiles.watch(folder):
            for change_info, file in changes:
                file_path = pathlib.Path(file)
                # print message
                print_event_message(change_info, file_path)
                # synchronize files and show file difference in case of file modification
                rsync_and_diff(change_info, file_path, monitored_folder, temp_dir)
                # print size folder
                print_folder_size(monitored_folder, monitored_folder.stat().st_size)
