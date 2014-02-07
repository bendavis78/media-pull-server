from distutils.core import setup

setup(
    name='media-pull-server',
    version='0.1dev',
    py_modules=['mediaserver'],
    install_requires=['twisted', 'paramiko'],
    license='Creative Commons Attribution-Noncommercial-Share Alike license',
    long_description=open('README.md').read(),
    entry_points={
        'console_scripts': {
            'mediaserver = mediaserver:cmdline'
        }
    }
)
