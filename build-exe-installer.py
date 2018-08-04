# FIXME: this contains copy/pasta from setup.py
import configparser
import os
import platform
import re
import shutil
import subprocess
import sys


assert platform.system() == 'Windows', "this script must be ran on windows"


# setup.py copy pasta
def get_requirements():
    with open('requirements.txt', 'r') as file:
        for line in map(str.strip, file):
            if (not line.startswith('#')) and line:
                yield line


# setup.py copy pasta
def find_metadata():
    with open(os.path.join('porcupine', '__init__.py')) as file:
        content = file.read()

    result = dict(re.findall(
        r'''^__(author|copyright|license)__ = ['"](.*)['"]$''',
        content, re.MULTILINE))
    assert result.keys() == {'author', 'copyright', 'license'}, result

    # version is defined like this: __version__ = '%d.%d.%d' % version_info
    version_info = re.search(r'^version_info = \((\d+), (\d+), (\d+)\)',
                             content, re.MULTILINE).groups()
    result['version'] = '%s.%s.%s' % version_info

    return result


def get_frozen_requirements_in_a_crazy_way():
    subprocess.check_call([sys.executable, '-m', 'venv', 'temp_env'])

    try:
        subprocess.check_call([
            r'temp_env\Scripts\python.exe', '-m',
            'pip', 'install', '-r', 'requirements.txt'])
        frozen = subprocess.check_output([
            r'temp_env\Scripts\python.exe', '-m', 'pip', 'freeze'
        ]).decode('utf-8').strip().splitlines()
    finally:
        shutil.rmtree('temp_venv')

    return [requirement for requirement in frozen
            if not requirement.lower().startswith('porcupine==')]


def create_pynsist_cfg():
    parser = configparser.ConfigParser()
    parser['Application'] = {
        'name': 'Porcupine',
        'version': find_metadata()['version'],
        'entry_point': 'porcupine.__main__:main',    # setup.py copy pasta
        # TODO: icon
        'license_file': 'LICENSE',
    }
    parser['Python'] = {
        'version': '%d.%d.%d' % sys.version_info[:3],
    }
    parser['Include'] = {
        'pypi_wheels': '\n'.join(get_frozen_requirements_in_a_crazy_way()),
        'files': 'porcupine/images',
    }

    with open('pynsist.cfg', 'w') as file:
        parser.write(file)


def run_pynsist():
    subprocess.check_call([sys.executable, '-m', 'nsist', 'pynsist.cfg'])


def main():
    create_pynsist_cfg()
    run_pynsist()


if __name__ == '__main__':
    main()
