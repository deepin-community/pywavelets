#!/usr/bin/env python
#-*- coding: utf-8 -*-

import os
import sys
import subprocess
import textwrap
import warnings
from functools import partial
from distutils.sysconfig import get_python_inc

import setuptools
from setuptools import setup, Extension
from setuptools.command.test import test as TestCommand

MAJOR = 1
MINOR = 4
MICRO = 1
ISRELEASED = True
VERSION = '%d.%d.%d' % (MAJOR, MINOR, MICRO)


# Return the git revision as a string
def git_version():
    def _minimal_ext_cmd(cmd):
        # construct minimal environment
        env = {}
        for k in ['SYSTEMROOT', 'PATH']:
            v = os.environ.get(k)
            if v is not None:
                env[k] = v
        # LANGUAGE is used on win32
        env['LANGUAGE'] = 'C'
        env['LANG'] = 'C'
        env['LC_ALL'] = 'C'
        out = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                               env=env).communicate()[0]
        return out

    try:
        out = _minimal_ext_cmd(['git', 'rev-parse', 'HEAD'])
        GIT_REVISION = out.strip().decode('ascii')
    except OSError:
        GIT_REVISION = "Unknown"

    return GIT_REVISION


def get_version_info():
    # Adding the git rev number needs to be done inside
    # write_version_py(), otherwise the import of pywt.version messes
    # up the build under Python 3.
    FULLVERSION = VERSION
    if os.path.exists('.git'):
        GIT_REVISION = git_version()
    elif os.path.exists('pywt/version.py'):
        # must be a source distribution, use existing version file
        # load it as a separate module to not load pywt/__init__.py
        import types
        from importlib.machinery import SourceFileLoader
        loader = SourceFileLoader('pywt.version', 'pywt/version.py')
        version = types.ModuleType(loader.name)
        loader.exec_module(version)
        GIT_REVISION = version.git_revision
    else:
        GIT_REVISION = "Unknown"

    if not ISRELEASED:
        FULLVERSION += '.dev0+' + GIT_REVISION[:7]

    return FULLVERSION, GIT_REVISION


def write_version_py(filename='pywt/version.py'):
    cnt = """
# THIS FILE IS GENERATED FROM PYWAVELETS SETUP.PY
short_version = '%(version)s'
version = '%(version)s'
full_version = '%(full_version)s'
git_revision = '%(git_revision)s'
release = %(isrelease)s

if not release:
    version = full_version
"""
    FULLVERSION, GIT_REVISION = get_version_info()

    with open(filename, 'w') as a:
        a.write(cnt % {'version': VERSION,
                       'full_version': FULLVERSION,
                       'git_revision': GIT_REVISION,
                       'isrelease': str(ISRELEASED)})


# BEFORE importing distutils, remove MANIFEST. distutils doesn't properly
# update it when the contents of directories change.
if os.path.exists('MANIFEST'):
    os.remove('MANIFEST')


if sys.platform == "darwin":
    # Don't create resource files on OS X tar.
    os.environ["COPY_EXTENDED_ATTRIBUTES_DISABLE"] = "true"
    os.environ["COPYFILE_DISABLE"] = "true"


make_ext_path = partial(os.path.join, "pywt", "_extensions")

sources = ["c/common.c", "c/convolution.c", "c/wt.c", "c/wavelets.c", "c/cwt.c"]
sources = list(map(make_ext_path, sources))
source_templates = ["c/convolution.template.c", "c/wt.template.c", "c/cwt.template.c"]
source_templates = list(map(make_ext_path, source_templates))
headers = ["c/templating.h", "c/wavelets_coeffs.h",
            "c/common.h", "c/convolution.h", "c/wt.h", "c/wavelets.h", "c/cwt.h"]
headers = list(map(make_ext_path, headers))
header_templates = ["c/convolution.template.h", "c/wt.template.h",
                    "c/wavelets_coeffs.template.h", "c/cwt.template.h"]
header_templates = list(map(make_ext_path, header_templates))


def get_cython_sources(use_cython):
    cython_modules = ['_pywt', '_dwt', '_swt', '_cwt']
    cython_sources = [('{0}.pyx' if use_cython else '{0}.c').format(module)
                      for module in cython_modules]
    return cython_modules, cython_sources


c_macros = [("PY_EXTENSION", None), ]
cython_macros = []

#c99_test_c = """#include <complex.h>
#int main(int argc, char** argv) { float complex a;  return(0); }"""

if 'USE_C99_COMPLEX' in os.environ:
    use_c99 = bool(int(os.environ['USE_C99_COMPLEX']))
else:
    # default to False on non-posix platforms
    # (MSVC doesn't support C99 complex)
    if os.name == 'posix':
        use_c99 = True
    else:
        use_c99 = False
if use_c99:
    c_macros += [("HAVE_C99_COMPLEX", None), ]
    # avoid compiler warnings:  tell Cython to use C99 complex types
    cython_macros += [('CYTHON_CCOMPLEX', 1), ]
    pxi_defines = dict(HAVE_C99_CPLX=1)
    py_defines = dict(_have_c99_complex=1)
else:
    pxi_defines = dict(HAVE_C99_CPLX=0)
    py_defines = dict(_have_c99_complex=0)

# write a file config.pxi that can be included by other .pyx files to determine
# whether or not C99 complex is supported at compile-time
defines_pxi = os.path.join(
    os.path.dirname(__file__), 'pywt', '_extensions', 'config.pxi')
with open(defines_pxi, 'w') as fd:
    fd.write("# Autogenerated file containing Cython compile-time defines\n\n")
    for k, v in pxi_defines.items():
        fd.write('DEF %s = %d\n' % (k.upper(), int(v)))

defines_py = os.path.join(
    os.path.dirname(__file__), 'pywt', '_c99_config.py')
with open(defines_py, 'w') as fd:
    fd.write("# Autogenerated file containing compile-time definitions\n\n")
    for k, v in py_defines.items():
        fd.write('%s = %d\n' % (k, int(v)))

cythonize_opts = {'language_level': '3'}
if os.environ.get("CYTHON_TRACE"):
    cythonize_opts['linetrace'] = True
    cython_macros.append(("CYTHON_TRACE_NOGIL", 1))

# By default C object files are rebuilt for every extension
# C files must be built once only for coverage to work
c_lib = ('c_wt', {'sources': sources,
                  'depends': source_templates + header_templates + headers,
                  'include_dirs': [make_ext_path("c"), get_python_inc()],
                  'macros': c_macros, })

def get_ext_modules(use_cython):
    from numpy import get_include as get_numpy_include
    cython_modules, cython_sources = get_cython_sources(use_cython)
    ext_modules = [
        Extension('pywt._extensions.{0}'.format(module),
                  sources=[make_ext_path(source)],
                  # Doesn't automatically rebuild if library changes
                  depends=c_lib[1]['sources'] + c_lib[1]['depends'],
                  include_dirs=[make_ext_path("c"), get_numpy_include()],
                  define_macros=c_macros + cython_macros,
                  libraries=[c_lib[0]],)
        for module, source, in zip(cython_modules, cython_sources)
    ]
    return ext_modules


from setuptools.command.develop import develop
class develop_build_clib(develop):
    """Ugly monkeypatching to get clib to build for development installs

    See coverage comment above for why we don't just let libraries be built
    via extensions.

    All this is a copy of the relevant part of `install_for_development`
    for current master (Sep 2016) of setuptools.

    Note: if you want to build in-place with ``python setup.py build_ext``,
    that will only work if you first do ``python setup.py build_clib``.

    """
    def install_for_development(self):
        self.run_command('egg_info')

        # Build extensions in-place (the next 7 lines are the monkeypatch)
        import glob
        hitlist = glob.glob(os.path.join('build', '*', 'libc_wt.*'))
        if hitlist:
            # Remove existing clib - running build_clib twice in a row fails
            os.remove(hitlist[0])
        self.reinitialize_command('build_clib', inplace=1)
        self.run_command('build_clib')

        self.reinitialize_command('build_ext', inplace=1)
        self.run_command('build_ext')

        try:
            self.install_site_py()  # ensure that target dir is site-safe
        except AttributeError:
            # setuptools 0.49 removed install_site_py
            pass

        if setuptools.bootstrap_install_from:
            self.easy_install(setuptools.bootstrap_install_from)
            setuptools.bootstrap_install_from = None

        # create an .egg-link in the installation dir, pointing to our egg
        from distutils import log
        log.info("Creating %s (link to %s)", self.egg_link, self.egg_base)
        if not self.dry_run:
            with open(self.egg_link, "w") as f:
                f.write(self.egg_path + "\n" + self.setup_path)
        # postprocess the installed distro, fixing up .pth, installing scripts,
        # and handling requirements
        self.process_distribution(None, self.dist, not self.no_deps)


def parse_setuppy_commands():
    """Check the commands and respond appropriately.  Disable broken commands.

    Return a boolean value for whether or not to run the build or not (avoid
    import NumPy or parsing Cython and template files if False).
    """
    args = sys.argv[1:]

    if not args:
        # User forgot to give an argument probably, let setuptools handle that.
        return True

    info_commands = ['--help-commands', '--name', '--version', '-V',
                     '--fullname', '--author', '--author-email',
                     '--maintainer', '--maintainer-email', '--contact',
                     '--contact-email', '--url', '--license', '--description',
                     '--long-description', '--platforms', '--classifiers',
                     '--keywords', '--provides', '--requires', '--obsoletes']

    for command in info_commands:
        if command in args:
            return False

    # Note that 'alias', 'saveopts' and 'setopt' commands also seem to work
    # fine as they are, but are usually used together with one of the commands
    # below and not standalone.  Hence they're not added to good_commands.
    good_commands = ('develop', 'sdist', 'build', 'build_ext', 'build_py',
                     'build_clib', 'build_scripts', 'bdist_wheel', 'bdist_rpm',
                     'bdist_wininst', 'bdist_msi', 'bdist_mpkg',
                     'build_sphinx')

    for command in good_commands:
        if command in args:
            return True

    # The following commands are supported, but we need to show more
    # useful messages to the user
    if 'install' in args:
        print(textwrap.dedent("""
            Note: if you need reliable uninstall behavior, then install
            with pip instead of using `setup.py install`:

              - `pip install .`       (from a git repo or downloaded source
                                       release)
              - `pip install PyWavelets`   (last PyWavelets release on PyPI)

            """))
        return True

    if '--help' in args or '-h' in sys.argv[1]:
        print(textwrap.dedent("""
            PyWavelets-specific help
            ------------------------

            To install PyWavelets from here with reliable uninstall, we recommend
            that you use `pip install .`. To install the latest PyWavelets release
            from PyPI, use `pip install PyWavelets`.

            For help with build/installation issues, please ask on the
            PyWavelets mailing list.  If you are sure that you have run
            into a bug, please report it at https://github.com/PyWavelets/pywt/issues.

            Setuptools commands help
            ------------------------
            """))
        return False


    # The following commands aren't supported.  They can only be executed when
    # the user explicitly adds a --force command-line argument.
    bad_commands = dict(
        test="""
            `setup.py test` is not supported.  Use one of the following
            instead:

              - `>>> pywt.test()`           (run tests for installed PyWavelets
                                             from within an interpreter)
            """,
        upload="""
            `setup.py upload` is not supported, because it's insecure.
            Instead, build what you want to upload and upload those files
            with `twine upload -s <filenames>` instead.
            """,
        upload_docs="`setup.py upload_docs` is not supported",
        easy_install="`setup.py easy_install` is not supported",
        clean="""
            `setup.py clean` is not supported, use one of the following instead:

              - `git clean -xdf` (cleans all files)
              - `git clean -Xdf` (cleans all versioned files, doesn't touch
                                  files that aren't checked into the git repo)
            """,
        check="`setup.py check` is not supported",
        register="`setup.py register` is not supported",
        bdist_dumb="`setup.py bdist_dumb` is not supported",
        bdist="`setup.py bdist` is not supported",
        flake8="`setup.py flake8` is not supported, use flake8 standalone",
        )
    bad_commands['nosetests'] = bad_commands['test']
    for command in ('upload_docs', 'easy_install', 'bdist', 'bdist_dumb',
                     'register', 'check', 'install_data', 'install_headers',
                     'install_lib', 'install_scripts', ):
        bad_commands[command] = "`setup.py %s` is not supported" % command

    for command in bad_commands.keys():
        if command in args:
            print(textwrap.dedent(bad_commands[command]) +
                  "\nAdd `--force` to your command to use it anyway if you "
                  "must (unsupported).\n")
            sys.exit(1)

    # Commands that do more than print info, but also don't need Cython and
    # template parsing.
    other_commands = ['egg_info', 'install_egg_info', 'rotate']
    for command in other_commands:
        if command in args:
            return False

    # If we got here, we didn't detect what setup.py command was given
    warnings.warn("Unrecognized setuptools command, proceeding with "
                  "generating Cython sources and expanding templates")
    return True


class PyTest(TestCommand):
    user_options = [('pytest-args=', 'a', "Arguments to pass to py.test")]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.pytest_args = []

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        #import here, cause outside the eggs aren't loaded
        import pytest
        errno = pytest.main(self.pytest_args)
        sys.exit(errno)


def setup_package():
    # Rewrite the version file every time
    write_version_py()

    metadata = dict(
        name="PyWavelets",
        maintainer="The PyWavelets Developers",
        maintainer_email="pywavelets@googlegroups.com",
        url="https://github.com/PyWavelets/pywt",
        download_url="https://github.com/PyWavelets/pywt/releases",
        license="MIT",
        description="PyWavelets, wavelet transform module",
        long_description="""\
        PyWavelets is a Python wavelet transforms module that includes:

        * nD Forward and Inverse Discrete Wavelet Transform (DWT and IDWT)
        * 1D and 2D Forward and Inverse Stationary Wavelet Transform (Undecimated Wavelet Transform)
        * 1D and 2D Wavelet Packet decomposition and reconstruction
        * 1D Continuous Wavelet Tranfsorm
        * Computing Approximations of wavelet and scaling functions
        * Over 100 built-in wavelet filters and support for custom wavelets
        * Single and double precision calculations
        * Real and complex calculations
        * Results compatible with Matlab Wavelet Toolbox (TM)
        """,
        keywords=["wavelets", "wavelet transform", "DWT", "SWT", "CWT", "scientific"],
        classifiers=[
            "Development Status :: 5 - Production/Stable",
            "Intended Audience :: Developers",
            "Intended Audience :: Education",
            "Intended Audience :: Science/Research",
            "License :: OSI Approved :: MIT License",
            "Operating System :: OS Independent",
            "Programming Language :: C",
            "Programming Language :: Python",
            "Programming Language :: Python :: 3",
            "Programming Language :: Python :: 3.8",
            "Programming Language :: Python :: 3.9",
            "Programming Language :: Python :: 3.10",
            "Programming Language :: Python :: 3.11",
            "Topic :: Software Development :: Libraries :: Python Modules"
        ],
        platforms=["Windows", "Linux", "Solaris", "Mac OS-X", "Unix"],
        version=get_version_info()[0],

        packages=['pywt', 'pywt._extensions', 'pywt.data'],
        package_data={'pywt.data': ['*.npy', '*.npz'],
                      'pywt': ['tests/*.py', 'tests/data/*.npz',
                               'tests/data/*.py']},
        libraries=[c_lib],
        cmdclass={'develop': develop_build_clib, 'test': PyTest},
        tests_require=['pytest'],

        install_requires=["numpy>=1.17.3"],
        python_requires=">=3.8",
    )

    if "--force" in sys.argv:
        run_build = True
        sys.argv.remove('--force')
    else:
        # Raise errors for unsupported commands, improve help output, etc.
        run_build = parse_setuppy_commands()

    if run_build:
        # This imports numpy and Cython, so only do that if we're actually
        # building and not for, e.g., pip grabbing metadata.
        # See gh-397 for details.
        try:
            from Cython.Build import cythonize
            USE_CYTHON = True
        except ImportError:
            USE_CYTHON = False
            if not os.path.exists(os.path.join('pywt', '_extensions', '_pywt.c')):
                msg = ("Cython must be installed when working with a development "
                       "version of PyWavelets")
                raise RuntimeError(msg)

        ext_modules = get_ext_modules(USE_CYTHON)
        if USE_CYTHON:
            ext_modules = cythonize(ext_modules, compiler_directives=cythonize_opts)

        metadata['ext_modules'] = ext_modules

    setup(**metadata)


if __name__ == '__main__':
    setup_package()
